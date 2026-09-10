import os
import uuid
from collections import defaultdict
from datetime import date

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Count, DateField, Max, Min, Q
from django.db.models.functions import Cast, Coalesce, TruncMonth
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User, Student, Company, StudentSkill
from accounts.permissions import IsStudent, IsCompany, IsAdminUserRole
from scrape_jobs.models import JobCategory, MarketRole, Skill
from job_listings.matching import proficiency_value, skill_score
from job_listings.models import JobListing, ScrapeLog
from scrape_jobs.serializers import ScrapeLogSerializer
from resources.models import Certificate, LearningResource  # Certificate: admin dashboard only
from resources.providers import authority_index, get_provider, provider_names
from resources.relevance import DEFAULT_PER_SKILL, free_status, related_resources
from resources.file_validation import InvalidUpload, validate_document

from .models import Announcement
from .notifications import build_feed
from .serializers import AnnouncementSerializer


DEMAND_TREND_MONTHS = 12
STALE_MARKET_DATA_DAYS = 31

# How many of the most-demanded skills define "critical" for a target role.
CRITICAL_SKILL_COUNT = 12
# Soft skills are reported alongside, not inside, the technical gap list.
SOFT_SKILL_CATEGORY = 'Soft Skill'
SOFT_SKILL_COUNT = 6
# How many classified adverts a Market Role needs before the analysis will
# scope to it. One: if the market has advertised a career at all, the student
# who wants it gets the answer that career's adverts give, rather than being
# widened into a career area they did not ask about.
#
# The trade-off is real and is reported rather than hidden -- a demand
# percentage computed from a single advert describes that advert, not the
# market -- so every response carries the advert count the figure rests on
# and the page shows it next to the number.
#
# Only a role with no adverts at all now falls back.
MIN_LISTINGS_FOR_TARGET = 1
# Demand thresholds (share of listings asking for the skill) -> priority.
HIGH_PRIORITY_DEMAND = 30
MEDIUM_PRIORITY_DEMAND = 15
# How many learning resources the skill-gap page recommends, and how many of
# them any single skill may claim -- the cap is what stops one well-covered
# skill filling every slot ahead of higher-priority gaps.
MAX_RECOMMENDED_RESOURCES = 6
MAX_RESOURCES_PER_SKILL = 2


def shift_month(month, offset):
    """Return the first day of ``month`` shifted by ``offset`` months."""
    month_index = month.year * 12 + month.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)
    return date(year, zero_based_month + 1, 1)


def month_key(value):
    if hasattr(value, 'date'):
        value = value.date()
    return value.replace(day=1)


def percentage_change(current, previous):
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)



def live_market_jobs():
    """Scraped adverts a student could still apply to today.

    The skill gap answers "what should I learn to be hired now", so it is
    measured against adverts that are still open. A posting JobStreet dropped
    two quarters ago describes a vacancy that has been filled; letting it set
    the requirement tells a student to chase demand that no longer exists.

    Deliberately narrower than what the demand *chart* uses. A 12-month trend
    needs closed postings or there is no trend -- that is history, and history
    is what a trend is made of. This is the present tense, and the two are
    reported with different labels because they answer different questions.

    ACTIVE is maintained by job_listings.expiry: JobStreet keeps a posting for
    about 30 days, so anything older is marked CLOSED rather than deleted.
    """
    return JobListing.objects.filter(
        source_type=JobListing.SourceType.SCRAPED,
        status=JobListing.Status.ACTIVE,
    )


def default_target(student):
    """The student's first target row, or None."""
    return (student.target_roles
            .select_related('market_role')
            .order_by('added_time', 'id')
            .first())


def default_target_role(student):
    """The student's first target Market Role, or None."""
    target = default_target(student)
    return target.market_role if target else None


def default_target_area(student):
    """The Broad Area behind the student's first target Market Role.

    Broad Area never decides which role an advert belongs to. It is used here
    only to widen the *analysis* when one role has too few adverts to measure,
    which is a reporting decision and is reported as such.
    """
    role = default_target_role(student)
    return role.broad_area if role is not None else None


def default_target_scope(student):
    """The widest usable scope for a student who named neither role nor area.

    Returns ``(role, broad_area)``, either of which may be None.
    """
    market = live_market_jobs()

    # The role is what the student actually chose, so it is tried first. Its
    # own Broad Area is the fallback, handled inside build_skill_gap rather
    # than here so the page can say which level answered.
    role = default_target_role(student)
    if role is not None and market.filter(
            market_role=role).count() >= MIN_LISTINGS_FOR_TARGET:
        return None, None

    area = default_target_area(student)
    if area:
        matched = market.filter(market_role__broad_area=area).count()
        if matched >= MIN_LISTINGS_FOR_TARGET:
            return None, area

    # Neither has enough evidence. Report whichever the student actually holds
    # so data_quality still says has_target truthfully and the page explains a
    # thin sample rather than claiming no target was set.
    return None, area or None


def collection_effort():
    """month -> how many successful scrape runs happened in it.

    A month with no run is not a month with no demand -- it is a month nobody
    looked, and the two are indistinguishable in the listing table because
    both give a low count. Treating them as the same is what produced a
    "+880.9%" three-month change out of nothing: the scraper ran three times
    in May, not at all in July, and twice in August, so the chart was drawing
    our own collection schedule and calling it the labour market.

    The run *count* matters as much as the fact of running. One run in June
    collected 3 adverts; two runs in August collected 418. Comparing those two
    months measures how hard we looked, not how much was advertised.

    Read from ScrapeLog rather than inferred from posted_date, because the log
    is the actual record of when collection happened. PARTIAL counts: some
    pages were blocked, but the month was still collected.
    """
    from job_listings.models import ScrapeLog

    effort = {}
    for row in (ScrapeLog.objects
                .filter(status__in=(ScrapeLog.Status.SUCCESS,
                                    ScrapeLog.Status.PARTIAL))
                .annotate(month=TruncMonth('started_at'))
                .values('month')
                .annotate(runs=Count('id'))):
        if row['month']:
            effort[month_key(row['month'])] = row['runs']
    return effort


def build_market_demand(student, months=DEMAND_TREND_MONTHS, broad_area=None,
                        market_role=None):
    """Build an honest market time series for the student's dashboard.

    Scoped by Market Role, or by Broad Area when a wider view is wanted. Both
    the chart and the skill gap now speak the same vocabulary as the student's
    own target, which is the point of having one classification target.

    ``broad_area`` and ``market_role`` let the student explore any career's
    trend, not only their own. With neither, it falls back to their saved
    target and then to the whole market.

    Months outside the observed collection window are returned as ``null``
    rather than zero so a scraper gap is not presented as a collapse in
    employer demand.
    """
    today = timezone.localdate()
    chart_end = today.replace(day=1)
    chart_start = shift_month(chart_end, -(months - 1))
    chart_end_exclusive = shift_month(chart_end, 1)

    if broad_area is None and market_role is None:
        target = default_target_role(student)
        if target is not None:
            market_role = target.name
            broad_area = target.broad_area

    dated_market_jobs = (
        JobListing.objects
        .filter(source_type=JobListing.SourceType.SCRAPED)
        .annotate(
            market_date=Coalesce(
                'posted_date',
                Cast('posted_time', output_field=DateField()),
            ),
        )
    )
    bounds = dated_market_jobs.aggregate(
        first_date=Min('market_date'),
        latest_date=Max('market_date'),
    )
    first_date = bounds['first_date']
    latest_date = bounds['latest_date']

    jobs_in_period = dated_market_jobs.filter(
        market_date__gte=chart_start,
        market_date__lt=chart_end_exclusive,
    )
    scoped_jobs = jobs_in_period
    if market_role:
        # A Market Role is narrower than its Broad Area, so it wins.
        scoped_jobs = scoped_jobs.filter(market_role__name=market_role)
    elif broad_area:
        scoped_jobs = scoped_jobs.filter(market_role__broad_area=broad_area)

    grouped_counts = scoped_jobs.annotate(
        month=TruncMonth('market_date'),
    ).values('month').annotate(
        job_count=Count('id', distinct=True),
    ).order_by('month')
    counts_by_month = {
        month_key(row['month']): row['job_count']
        for row in grouped_counts
    }

    first_observed_month = month_key(first_date) if first_date else None
    latest_observed_month = month_key(latest_date) if latest_date else None
    effort = collection_effort()
    collected = set(effort)
    # The month in progress is short by however many days are left in it, so
    # its count is not comparable with a finished one and is never used as
    # evidence of a rise or a fall.
    this_month = today.replace(day=1)

    series = []
    for offset in range(months):
        current_month = shift_month(chart_start, offset)
        was_collected = current_month in collected
        partial = was_collected and current_month == this_month
        series.append({
            'month': current_month.isoformat(),
            'label': current_month.strftime('%b %Y'),
            # None in two cases, and 0 in neither of them:
            #
            #   * nobody collected this month -- a gap in the line, not a
            #     month with no jobs in it;
            #   * the month is still running -- one day of September is not a
            #     fall from August, but plotted as a point it is indis-
            #     tinguishable from one, and it drew a cliff to zero.
            #
            # The running month's count is still returned, below, as its own
            # value. It is reported, just not drawn as though it were final.
            'job_count': (counts_by_month.get(current_month, 0)
                          if was_collected and not partial else None),
            'observed': was_collected,
            'partial': partial,
        })

    # The change is reported only when both windows were actually collected
    # and neither is still running. Anything else is a comparison between a
    # month we looked at and a month we did not, which is not a change in
    # demand -- so it is withheld, and the reason is returned with it.
    change = None
    change_basis = 'NOT_ENOUGH_COLLECTED'
    finished = sorted(month for month in collected if month < this_month)

    if len(finished) >= 2:
        recent, earlier = finished[-1], finished[-2]
        # Equal effort or nothing. Two months are comparable when the scraper
        # ran the same number of times in each; otherwise the difference
        # between them is our schedule, and reporting it as market movement
        # would be inventing a trend. Withholding is the honest answer, and
        # the basis says which it is so the page can explain rather than show
        # a bare dash.
        if effort.get(recent) == effort.get(earlier):
            change = percentage_change(counts_by_month.get(recent, 0),
                                       counts_by_month.get(earlier, 0))
            change_basis = 'MONTH_ON_MONTH'
        else:
            change_basis = 'UNEVEN_COLLECTION'
    elif len(finished) == 1:
        change_basis = 'SINGLE_MONTH'
    elif this_month in collected:
        change_basis = 'CURRENT_MONTH_ONLY'

    total_market_postings = jobs_in_period.count()

    # How many adverts were placed on a Market Role at all. Not gated on human
    # review: per-listing review was considered and dropped, because scraped
    # adverts lapse in about 30 days and the queue would never empty.
    #
    # The number means *classified*, not *checked*, and the label says so.
    # Ambiguous and unclassified adverts are deliberately excluded -- they are
    # the absence of a classification, not a category of demand.
    matched_postings = jobs_in_period.filter(market_role__isnull=False).count()

    standardization_coverage = (
        round(matched_postings / total_market_postings * 100, 1)
        if total_market_postings else 0
    )

    # Only Broad Areas that actually have adverts in this period appear: the
    # group-by drops empties, so a career area with nothing scraped behind it
    # is never offered as "in demand". Unclassified adverts have no Broad Area
    # and so cannot rank, which is correct -- they are the absence of a
    # classification, not an area of demand.
    top_areas = list(
        jobs_in_period
        .filter(market_role__isnull=False)
        .exclude(market_role__broad_area='')
        .values('market_role__broad_area')
        .annotate(job_count=Count('id', distinct=True))
        .order_by('-job_count', 'market_role__broad_area')[:5]
    )

    # Ranked by Market Role, which is the name a student recognises: "Data
    # Analyst", not the Broad Area shelf it sits on. Junior, plain and senior
    # Data Analyst adverts all count towards the one role, because career
    # level is normalized away from the occupational function.
    #
    # The ranking is reported alongside the number of adverts behind it: a
    # single-digit count must never read as the whole market.
    #
    # Scoped to the selection when there is one, so the list reads as "the
    # roles within this career area".
    role_jobs = scoped_jobs.filter(market_role__isnull=False)
    top_market_roles = list(
        role_jobs
        .values('market_role__name', 'market_role__broad_area')
        .annotate(job_count=Count('id', distinct=True))
        .order_by('-job_count', 'market_role__name')[:5]
    )
    market_role_postings = role_jobs.count()
    top_categories = list(
        jobs_in_period
        .filter(category__isnull=False)
        .values('category_id', 'category__category_name')
        .annotate(job_count=Count('id', distinct=True))
        .order_by('-job_count', 'category__category_name')[:5]
    )

    freshness_days = (today - latest_date).days if latest_date else None
    return {
        'mode': 'TARGET' if (market_role or broad_area) else 'OVERVIEW',
        'period_months': months,
        'title': (
            f'Demand Trend for {market_role}' if market_role
            else f'Demand Trend for {broad_area}' if broad_area
            else 'Technology Job Market Trend'
        ),
        'target_market_role': market_role,
        'target_broad_area': broad_area,
        'series': series,
        # Two totals, because they answer two questions and conflating them is
        # what made the dashboard read "486 postings" beside a jobs page
        # listing 278. `total_postings` is what a student can still apply to;
        # the 12-month figure is what the trend line is drawn from, and a
        # trend needs the closed months or it is not a trend.
        'total_postings': scoped_jobs.filter(
            status=JobListing.Status.ACTIVE).count(),
        'total_postings_in_period': scoped_jobs.count(),
        # The month still running, reported beside the chart rather than
        # plotted in it. Null when this month has not been collected.
        'month_in_progress': ({
            'label': this_month.strftime('%b %Y'),
            'job_count': counts_by_month.get(this_month, 0),
        } if this_month in collected else None),
        # Renamed: it is no longer a fixed three-month window. It compares
        # the two most recently completed months, and only when the scraper
        # ran equally often in both.
        'demand_change_percentage': change,
        # Why the number is there, or why it is not, so the page can explain
        # instead of printing a figure with no basis.
        'change_basis': change_basis,
        'collected_months': len(collected),
        'top_broad_areas': [
            {
                'name': row['market_role__broad_area'],
                'job_count': row['job_count'],
            }
            for row in top_areas
        ],
        'top_market_roles': [
            {
                'name': row['market_role__name'],
                'broad_area': row['market_role__broad_area'],
                'job_count': row['job_count'],
            }
            for row in top_market_roles
        ],
        # How many adverts the role ranking rests on. Reported so the UI can
        # say so rather than presenting 29 adverts as the market.
        'market_role_postings': market_role_postings,
        'top_categories': [
            {
                'id': row['category_id'],
                'category_name': row['category__category_name'],
                'job_count': row['job_count'],
            }
            for row in top_categories
        ],
        'data_quality': {
            'first_observed_date': first_date,
            'latest_observed_date': latest_date,
            'freshness_days': freshness_days,
            'is_stale': (
                freshness_days is None
                or freshness_days > STALE_MARKET_DATA_DAYS
            ),
            'market_postings_in_period': total_market_postings,
            # Still open on the source portal, and therefore the only ones the
            # skill gap measures against.
            'live_market_postings': jobs_in_period.filter(
                status=JobListing.Status.ACTIVE).count(),
            # Placed by the normalizer. Named "matched" rather than
            # "standardized"/"verified" because that is what it is: no human
            # confirms these, and the label should not imply one did.
            'matched_postings_in_period': matched_postings,
            'matched_coverage_percentage': standardization_coverage,
        },
    }



#: The one proficiency scale, imported rather than restated. Job matching and
#: the skill gap disagreeing about what "Intermediate" is worth would make two
#: numbers on the same page incomparable.
READINESS_MATCHED = 'MATCHED'
READINESS_DEVELOPING = 'DEVELOPING'
READINESS_MISSING = 'MISSING'


def required_levels(scoped_jobs):
    """{skill_id: (required_level, distribution)} for a set of adverts.

    The requirement is the level *most* adverts ask for, not the highest one
    any advert asks for. A single Advanced posting among eight Intermediate
    ones does not make Advanced the market requirement, and reporting it that
    way would tell most of a cohort they are unready for a role they can
    already do.

    The distribution comes back with it so the page can show the spread rather
    than asking the student to trust a single word.
    """
    from job_listings.models import JobSkill

    rows = (JobSkill.objects
            .filter(job__in=scoped_jobs)
            .values('skill_id', 'required_level')
            .annotate(n=Count('id')))

    spread = defaultdict(dict)
    for row in rows:
        spread[row['skill_id']][row['required_level']] = row['n']

    resolved = {}
    for skill_id, distribution in spread.items():
        # Ties break towards the higher level: when the market is evenly
        # split, understating the requirement is the more harmful error.
        level = max(distribution.items(),
                    key=lambda item: (item[1], proficiency_value(item[0])))[0]
        resolved[skill_id] = (level, distribution)
    return resolved


def readiness(student_level, required_level):
    """MATCHED / DEVELOPING / MISSING for one skill."""
    if student_level is None:
        return READINESS_MISSING
    if proficiency_value(student_level) >= proficiency_value(required_level):
        return READINESS_MATCHED
    return READINESS_DEVELOPING


def priority_for(demand_percentage):
    if demand_percentage >= HIGH_PRIORITY_DEMAND:
        return 'HIGH'
    if demand_percentage >= MEDIUM_PRIORITY_DEMAND:
        return 'MEDIUM'
    return 'LOW'


def pick_resources_for_gap(missing_ids, per_skill=DEFAULT_PER_SKILL):
    """Related resources for each missing skill, grouped by skill.

    Grouped rather than pooled, because the page asks a different question than
    it used to. It once chose six resources across all the gaps and presented
    them as recommended learning, which forced two judgements it had no basis
    for: which skills deserved a slot at all, and which single course was best.
    A student closing a gap wants the courses for *this* skill, and to choose
    among them.

    ``missing_ids`` arrives in demand order, so the groups come back in the
    order worth working through.

    Each group carries a ``total`` beside its slice, so the page can offer
    "View more" without shipping 119 rows for C#.
    """
    if not missing_ids:
        return []

    # Built once for the page. The index composes what every registered adapter
    # claims to vendor, and rebuilding it per skill would repeat that work for
    # no benefit.
    authority = authority_index(
        get_provider(name) for name in provider_names())

    groups = []
    for skill in Skill.objects.filter(id__in=missing_ids):
        resources, total = related_resources(skill, limit=per_skill,
                                             authority=authority)
        if resources:
            groups.append({"skill": skill, "resources": resources,
                           "total": total})

    # Back into demand order: the queryset returns rows in whatever order the
    # database chose, and the priority order is the whole point of the list.
    position = {skill_id: index for index, skill_id in enumerate(missing_ids)}
    groups.sort(key=lambda group: position.get(group["skill"].id, len(position)))
    return groups


def build_skill_gap(student, broad_area=None, role=None, use_saved_target=True):
    """Compare the student's skills against real employer demand.

    Demand is scoped to a Market Role when one is given -- that is the whole
    point of the classification, and it is the vocabulary the student's own
    target is expressed in.

    Given neither, the student's own target resolves to whichever scope the
    market can actually answer -- see default_target_scope.

    A thin sample widens to the role's Broad Area and then to the whole
    market, rather than reporting a confident gap built on a handful of rows.
    Broad Area is used here to widen a *measurement*, never to decide which
    role an advert belongs to.
    """
    # "Nothing was asked for" and "the whole market was asked for" are two
    # different questions and used to arrive as the same empty query. Reading
    # both as the first meant a student who picked "explore by career area"
    # was answered with the saved target they had just stepped away from --
    # the page said "Not sure" and the analysis said "Data Engineer".
    if use_saved_target and broad_area is None and role is None:
        role = default_target_role(student)
        _, broad_area = default_target_scope(student)

    market_jobs = live_market_jobs()

    # Scope chain: role -> the role's own Broad Area -> whole market. Each step
    # is taken only when the one before it has too little evidence to analyse,
    # and which step answered is reported in data_quality so the page can say
    # so outright.
    role_listing_count = None
    fell_back_to_area = False
    if role is not None:
        role_jobs = market_jobs.filter(market_role=role)
        role_listing_count = role_jobs.count()
        if role_listing_count >= MIN_LISTINGS_FOR_TARGET:
            target_jobs = role_jobs
            scope_level = 'ROLE'
        else:
            broad_area = broad_area or role.broad_area
            fell_back_to_area = bool(broad_area)
            target_jobs = (
                market_jobs.filter(market_role__broad_area=broad_area)
                if fell_back_to_area else market_jobs.none()
            )
            scope_level = 'BROAD_AREA' if fell_back_to_area else 'MARKET'
    elif broad_area:
        target_jobs = market_jobs.filter(market_role__broad_area=broad_area)
        scope_level = 'BROAD_AREA'
    else:
        target_jobs = market_jobs.none()
        scope_level = 'MARKET'

    target_listing_count = target_jobs.count()

    use_target = (
        (role is not None or bool(broad_area))
        and target_listing_count >= MIN_LISTINGS_FOR_TARGET
    )
    if not use_target:
        scope_level = 'MARKET'
    scoped_jobs = target_jobs if use_target else market_jobs
    total_listings = scoped_jobs.count()

    demand_base = (
        Skill.objects
        .annotate(demand_count=Count(
            'job_skills',
            filter=Q(job_skills__job__in=scoped_jobs),
            distinct=True,
        ))
        .filter(demand_count__gt=0)
        .order_by('-demand_count', 'skill_name')
    )

    # Soft skills are ranked separately rather than competing with technical
    # ones. "Communication" appears in the boilerplate of ~76% of adverts, so
    # left in the same list it is the top gap for every career and drowns the
    # signal a student can actually act on.
    is_soft = Q(skill_category__iexact=SOFT_SKILL_CATEGORY)
    technical_rows = demand_base.exclude(is_soft)[:CRITICAL_SKILL_COUNT]
    soft_rows = demand_base.filter(is_soft)[:SOFT_SKILL_COUNT]

    owned_levels = {
        row.skill_id: row.skill_level
        for row in student.student_skills.select_related('skill')
    }

    # What the market asks for, per skill, from the adverts in scope.
    requirements = required_levels(scoped_jobs)

    def as_entry(skill):
        demand_percentage = (
            round(skill.demand_count / total_listings * 100, 1)
            if total_listings else 0
        )
        required_level, distribution = requirements.get(
            skill.id, (StudentSkill.SkillLevel.INTERMEDIATE, {}))
        student_level = owned_levels.get(skill.id)
        return {
            'skill_id': skill.id,
            'skill': skill.skill_name,
            'category': skill.skill_category,
            'demand_count': skill.demand_count,
            'demand_percentage': demand_percentage,
            # The three values that make a gap a gap. Holding a skill is not
            # the same as being ready for it: a student with Intermediate
            # Python against an Advanced requirement was previously counted as
            # a full match, which flattered the score and hid the actual gap.
            'required_level': required_level,
            'student_level': student_level,
            'level_distribution': distribution,
            'readiness_status': readiness(student_level, required_level),
        }

    # One entry per demanded skill, built once. matched/missing are views over
    # it, so a skill can appear in both without being counted twice anywhere
    # that matters.
    technical = []
    for skill in technical_rows:
        entry = as_entry(skill)
        if entry['student_level'] is not None:
            entry['skill_level'] = entry['student_level']
        if entry['readiness_status'] != READINESS_MATCHED:
            entry['priority_level'] = priority_for(entry['demand_percentage'])
        technical.append(entry)

    # MATCHED and DEVELOPING both mean the student holds the skill, so both
    # belong in `matched`. DEVELOPING is also a real gap, so it appears in
    # `missing` too: dropping it there would leave the student with no prompt
    # to close the distance, and dropping it from `matched` would deny them
    # credit for what they already have.
    matched = [row for row in technical
               if row['readiness_status'] != READINESS_MISSING]
    missing = [row for row in technical
               if row['readiness_status'] != READINESS_MATCHED]

    soft_skills = []
    for skill in soft_rows:
        entry = as_entry(skill)
        entry['held'] = skill.id in owned_levels
        if entry['held']:
            entry['skill_level'] = owned_levels[skill.id]
        soft_skills.append(entry)

    critical_total = len(technical)

    # The same proficiency formula the job recommendations use, so a student
    # comparing "78% match" on a listing with "78% ready" for the role is
    # comparing like with like. Counting skills held would answer a different
    # question and give a different number.
    required_points = sum(
        proficiency_value(row['required_level']) for row in technical)
    achieved_points = sum(
        skill_score(row['required_level'], row['student_level'])
        for row in technical)
    match_percentage = (
        round(achieved_points / required_points * 100)
        if required_points else 0
    )

    # Skills the student holds that are not in the critical list still belong
    # on the page — they are real, just not decisive for this target. Soft
    # skills are excluded here because they have their own section.
    critical_ids = {row['skill_id'] for row in matched + missing + soft_skills}
    other_skills = [
        {
            'skill_id': row.skill_id,
            'skill': row.skill.skill_name,
            'skill_level': row.skill_level,
        }
        for row in student.student_skills.select_related('skill')
        if row.skill_id not in critical_ids
    ]

    # `missing` is already in demand order, so it doubles as the priority
    # order for what to learn first. A developing skill belongs here: the
    # student needs resources to close the distance, not only to start.
    missing_ids = [row['skill_id'] for row in missing]
    priority_by_skill = {row['skill_id']: row['priority_level'] for row in missing}
    demand_by_skill = {row['skill_id']: row['demand_percentage'] for row in missing}
    resource_groups = pick_resources_for_gap(missing_ids)
    prices = free_status(
        resource.url
        for group in resource_groups for resource in group['resources'])

    return {
        'mode': 'TARGET' if use_target else 'OVERVIEW',
        'scope': scope_level,
        # The role the student picked, always reported even when the analysis
        # fell back -- the page must name the scope it actually used without
        # losing what was asked for.
        'target_role': role.name if role is not None else None,
        'target_broad_area': broad_area or None,
        'total_listings': total_listings,
        'critical_skill_count': critical_total,
        'match_percentage': match_percentage,
        'matched_skills': matched,
        'missing_skills': missing,
        'soft_skills': soft_skills,
        'other_skills': other_skills,
        # Grouped by skill, and named for what it is: the courses that
        # teach this skill, for the student to choose between. Not a best
        # course -- nothing in the catalogue knows a course's length, teaching
        # quality or fit, and an order implying otherwise would claim more than
        # the evidence carries.
        'resources_by_skill': [
            {
                'skill_id': group['skill'].id,
                'skill': group['skill'].skill_name,
                'skill_priority': priority_by_skill.get(group['skill'].id),
                'skill_demand_percentage': demand_by_skill.get(group['skill'].id),
                # How many exist in total, so "View more" knows whether it has
                # anything left to show.
                'total': group['total'],
                'resources': [
                    {
                        'id': resource.id,
                        'title': resource.title,
                        'platform': resource.platform,
                        'url': resource.url,
                        'type': resource.type,
                        # Present only when the provider actually stated a
                        # price. Absent means unknown, and the page leaves it
                        # out rather than rendering it as "Paid".
                        **({'is_free': prices[resource.url]}
                           if resource.url in prices else {}),
                    }
                    for resource in group['resources']
                ],
            }
            for group in resource_groups
        ],
        'data_quality': {
            'scope_level': scope_level,
            'target_listing_count': target_listing_count,
            'role_listing_count': role_listing_count,
            'market_listing_count': market_jobs.count(),
            # Role-level and area-level results are never equivalent, so the
            # two fallbacks are reported separately rather than as one flag.
            'fell_back_to_broad_area': fell_back_to_area,
            'fell_back_to_market': (
                (role is not None or bool(broad_area))
                and not use_target
            ),
            'has_target': (
                role is not None or bool(broad_area)
            ),
            'evidence_floor': MIN_LISTINGS_FOR_TARGET,
            'student_skill_count': len(owned_levels),
        },
    }


class SkillResourcesView(APIView):
    """
    GET /api/dashboard/skill-resources/?skill=<id>

    Every resource related to one skill -- what "View more" opens. The skill
    gap page carries a handful per skill so it stays readable; this is the rest
    of them, in the same deterministic order.

    Admission is unchanged and is not relaxed here: a resource appears only
    because the canonical extractor found this skill in the course's own words.
    A longer list is a longer list of the same evidence, never a weaker bar.
    """
    permission_classes = [IsStudent]

    def get(self, request):
        raw = request.query_params.get('skill')
        try:
            skill = Skill.objects.get(id=int(raw))
        except (TypeError, ValueError):
            return Response({'skill': ['Not a skill id.']},
                            status=status.HTTP_400_BAD_REQUEST)
        except Skill.DoesNotExist:
            return Response({'skill': ['No such skill.']},
                            status=status.HTTP_404_NOT_FOUND)

        authority = authority_index(
            get_provider(name) for name in provider_names())
        resources, total = related_resources(skill, limit=None,
                                             authority=authority)
        prices = free_status(resource.url for resource in resources)

        return Response({
            'skill_id': skill.id,
            'skill': skill.skill_name,
            'total': total,
            'resources': [
                {
                    'id': resource.id,
                    'title': resource.title,
                    'platform': resource.platform,
                    'url': resource.url,
                    'type': resource.type,
                    **({'is_free': prices[resource.url]}
                       if resource.url in prices else {}),
                }
                for resource in resources
            ],
        })


class StudentSkillGapView(APIView):
    """
    GET /api/dashboard/skill-gap/?role=<Market Role name>&broad_area=<name>
    Live skill-gap analysis for the logged-in student: which of the most
    demanded skills they already hold, which they are missing, and what to
    learn next.

    ``role`` and ``broad_area`` scope the analysis so the student can compare
    careers; omitted, it uses their saved target.
    """
    permission_classes = [IsStudent]

    def get(self, request):
        # ?scope=market is the browse path saying it means it: analyse the
        # whole market rather than falling back to the saved target. Any real
        # role or area still wins over it, so the flag can be sent freely.
        return Response(build_skill_gap(
            request.user.student_profile,
            resolve_broad_area(request.query_params.get('broad_area')),
            resolve_market_role(request.query_params.get('role')),
            use_saved_target=request.query_params.get('scope') != 'market',
        ))


def resolve_market_role(name):
    """Accept a name only if it names a real, active Market Role."""
    if not name:
        return None
    return MarketRole.objects.filter(name__iexact=str(name).strip(),
                                     is_active=True).first()


def resolve_broad_area(name):
    """Validate a Broad Area name, ignoring anything unknown."""
    if not name:
        return None
    cleaned = str(name).strip()
    return cleaned if MarketRole.objects.filter(
        broad_area__iexact=cleaned, is_active=True).exists() else None


def analysable_market_roles(min_listings=MIN_LISTINGS_FOR_TARGET):
    """Market Roles with enough classified adverts to measure against.

    A role below the floor is still a legitimate career and still selectable;
    it simply cannot carry a trustworthy skill profile yet, and the caller
    says so rather than quietly analysing four adverts.
    """
    return (
        MarketRole.objects
        .filter(is_active=True)
        .annotate(listing_count=Count(
            'job_listings',
            filter=Q(job_listings__source_type=JobListing.SourceType.SCRAPED,
                     job_listings__status=JobListing.Status.ACTIVE),
            distinct=True,
        ))
        .filter(listing_count__gte=min_listings)
        .order_by('-listing_count', 'name')
    )


class MarketRoleScopeView(APIView):
    """
    GET /api/dashboard/skill-gap/market-roles/
    The Market Roles the skill-gap analysis can answer for, grouped by Broad
    Area, with the advert count behind each so the student can see the
    evidence rather than take the number on trust.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        roles = analysable_market_roles()
        scraped = live_market_jobs()
        total = scraped.count()
        classified = scraped.filter(market_role__isnull=False).count()

        areas = {}
        for role in roles:
            bucket = areas.setdefault(role.broad_area or 'Other', {
                'name': role.broad_area or 'Other',
                'roles': [],
                'listing_count': 0,
            })
            bucket['roles'].append({
                'id': role.id,
                'name': role.name,
                'listing_count': role.listing_count,
            })
            bucket['listing_count'] += role.listing_count

        return Response({
            'evidence_floor': MIN_LISTINGS_FOR_TARGET,
            'results': sorted(areas.values(),
                              key=lambda area: -area['listing_count']),
            'coverage': {
                'scraped_total': total,
                # Classified means placed on a Market Role, not checked by a
                # person. Ambiguous and unclassified adverts are excluded --
                # counting them would report coverage the data does not have.
                'classified_total': classified,
                'classified_percentage': (
                    round(classified / total * 100, 1) if total else 0),
            },
        })


class MarketRoleProfileView(APIView):
    """
    GET /api/dashboard/market-role/?role=<name>
    What the market says about one Market Role: how many adverts it rests on,
    the career levels those adverts advertise, and the reviewed titles that
    map to it.

    There is no progression ladder here, and deliberately so. A ladder would
    be a claim about career structure that the scraped adverts do not make;
    what they do support is what employers are currently advertising and at
    which levels.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = resolve_market_role(request.query_params.get('role'))
        if role is None:
            return Response({'detail': 'Unknown or missing Market Role.'},
                            status=status.HTTP_400_BAD_REQUEST)

        listings = live_market_jobs().filter(market_role=role)
        levels = list(
            listings.exclude(career_level='')
            .values('career_level')
            .annotate(listing_count=Count('id', distinct=True))
            .order_by('-listing_count')
        )
        methods = list(
            listings.values('classification_method')
            .annotate(listing_count=Count('id', distinct=True))
            .order_by('-listing_count')
        )
        count = listings.count()

        return Response({
            'role': {
                'id': role.id,
                'name': role.name,
                'broad_area': role.broad_area,
                'description': role.description,
            },
            'listing_count': count,
            'analysable': count >= MIN_LISTINGS_FOR_TARGET,
            'evidence_floor': MIN_LISTINGS_FOR_TARGET,
            'career_levels': levels,
            # How this role's adverts were classified, so the evidence behind
            # a skill profile can be judged rather than assumed.
            'classification_methods': methods,
            'reviewed_titles': list(
                role.aliases.filter(reviewed=True)
                .order_by('normalized_title')
                .values_list('normalized_title', flat=True)
            ),
        })


class MarketDemandView(APIView):
    """
    GET /api/dashboard/market-demand/?role=<Market Role name>
    GET /api/dashboard/market-demand/?broad_area=<name>

    The demand-trend chart on its own, so the student can switch career
    without refetching the whole dashboard.
    """
    permission_classes = [IsStudent]

    def get(self, request):
        role = resolve_market_role(request.query_params.get('role'))
        return Response(build_market_demand(
            request.user.student_profile,
            broad_area=resolve_broad_area(request.query_params.get('broad_area')),
            market_role=role.name if role is not None else None,
        ))


class AnnouncementListView(generics.ListAPIView):
    """
    GET /api/dashboard/announcements/
    Returns announcements filtered by the caller's role:
      STUDENT  → EVERYONE + STUDENTS
      COMPANY  → EVERYONE + COMPANIES
      ADMIN    → all
    """
    serializer_class   = AnnouncementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = self.request.user.role
        if role == 'STUDENT':
            return Announcement.objects.filter(
                audience__in=['EVERYONE', 'STUDENTS']
            ).select_related('admin')
        if role == 'COMPANY':
            return Announcement.objects.filter(
                audience__in=['EVERYONE', 'COMPANIES']
            ).select_related('admin')
        return Announcement.objects.select_related('admin').all()


class AnnouncementCreateView(generics.CreateAPIView):
    """
    POST /api/dashboard/announcements/create/
    Admin only — creates a new announcement.
    """
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAdminUserRole]

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user.admin_profile)


class AnnouncementFileUploadView(APIView):
    """
    POST /api/dashboard/announcements/upload/
    Admin uploads a file (poster, document). Returns the absolute URL to store
    in supporting_doc — keeps the Announcement model a plain URLField per ERD.

    A poster or brochure is public: it is written into MEDIA_ROOT, which is
    served without authentication. That makes the file type the whole of the
    security boundary -- an .html or .svg accepted here would be served from
    the application's own origin and could run script against anyone who
    opened it. The extension is therefore never taken from the client's
    filename; the type is read from the file's own bytes and the stored name
    is generated.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            extension, _ = validate_document(file)
        except InvalidUpload as exc:
            message = str(exc).replace("A certificate must be",
                                       "A supporting document must be")
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)

        name = f"announcements/{uuid.uuid4().hex}{extension}"
        saved_path = default_storage.save(name, file)
        url = request.build_absolute_uri(settings.MEDIA_URL + saved_path)
        return Response({'url': url}, status=status.HTTP_201_CREATED)


class AnnouncementDeleteView(generics.DestroyAPIView):
    """
    DELETE /api/dashboard/announcements/<id>/
    Admin only — deletes an announcement.
    """
    queryset           = Announcement.objects.all()
    serializer_class   = AnnouncementSerializer
    permission_classes = [IsAdminUserRole]


class StudentNotificationsView(APIView):
    """
    GET /api/dashboard/notifications/

    What has happened to this student, newest first: application decisions,
    certificate and transcript outcomes, and announcements.

    Scoped to request.user's own student profile with no lookup parameter, so
    there is no way to read anybody else's. Derived from existing records
    rather than a Notification table -- see dashboard/notifications.py.
    """
    permission_classes = [IsStudent]

    def get(self, request):
        student = getattr(request.user, "student_profile", None)
        if student is None:
            return Response({"results": []})
        return Response({"results": build_feed(student)})


class StudentDashboardView(APIView):
    """
    GET /api/dashboard/student/
    Aggregated dashboard data for the logged-in student.
    Returns: latest announcements, job demand trends, certificate summary.
    """
    permission_classes = [IsStudent]

    def get(self, request):
        student = request.user.student_profile
        skills_count = student.student_skills.count()
        recent_applications = (
            student.job_applications
            .select_related('job__company')
            .order_by('-applied_time')[:3]
        )

        # The same audience rule AnnouncementListView applies. This aggregate
        # took .all(), so a student's dashboard showed announcements addressed
        # to companies -- the filtering existed but only on the endpoint nobody
        # was calling here.
        announcements = (
            Announcement.objects
            .filter(audience__in=['EVERYONE', 'STUDENTS'])
            .select_related('admin')[:3]
        )

        top_skills = (
            Skill.objects
            .annotate(demand_count=Count(
                'job_skills',
                filter=Q(job_skills__job__source_type='SCRAPED'),
            ))
            .filter(demand_count__gt=0)
            .order_by('-demand_count')[:5]
        )

        top_categories = (
            JobCategory.objects
            .annotate(job_count=Count(
                'job_listings',
                filter=Q(job_listings__source_type='SCRAPED'),
            ))
            .filter(job_count__gt=0)
            .order_by('-job_count')[:5]
        )

        return Response({
            'skills_count': skills_count,
            'applications_count': student.job_applications.count(),
            'recent_applications': [
                {
                    'id': application.id,
                    'job_id': application.job_id,
                    'job_title': (
                        application.job.job_title
                        or application.job.job_title
                    ),
                    'company_name': (
                        application.job.company.company_name
                        if application.job.company
                        else application.job.company_name or 'External employer'
                    ),
                    'status': application.status,
                    'applied_time': application.applied_time,
                }
                for application in recent_applications
            ],
            'announcements': AnnouncementSerializer(announcements, many=True, context={'request': request}).data,
            'market_demand': build_market_demand(student),
            'job_demand_trends': {
                'top_skills': [
                    {
                        'skill': s.skill_name,
                        'category': s.skill_category,
                        'demand_count': s.demand_count,
                    }
                    for s in top_skills
                ],
                'top_categories': [
                    {
                        'category_name': c.category_name,
                        'job_count': c.job_count,
                    }
                    for c in top_categories
                ],
            },
        })


class AdminDashboardView(APIView):
    """
    GET /api/dashboard/admin/
    System-wide KPIs for the admin: user counts, pending certs,
    scraped job stats, and recent scrape logs.
    """
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        stats = {
            'total_users': User.objects.count(),
            'total_students': Student.objects.count(),
            'total_companies': Company.objects.count(),
            'pending_certificates': Certificate.objects.filter(verified_status='PENDING').count(),
            'total_scraped_jobs': JobListing.objects.filter(source_type='SCRAPED').count(),
            'total_skills': Skill.objects.count(),
        }

        recent_logs = ScrapeLog.objects.all()[:5]
        recent_announcements = Announcement.objects.select_related('admin').all()[:5]

        return Response({
            'stats': stats,
            'recent_scrape_logs': ScrapeLogSerializer(recent_logs, many=True).data,
            'recent_announcements': AnnouncementSerializer(recent_announcements, many=True, context={'request': request}).data,
        })


class CompanyDashboardView(APIView):
    """
    GET /api/dashboard/company/
    Company dashboard with real hiring-pipeline stats.
    """
    permission_classes = [IsCompany]

    def get(self, request):
        from job_listings.models import JobListing, JobApplication

        company = request.user.company_profile

        active_listings    = JobListing.objects.filter(company=company, status='ACTIVE').count()
        total_applications = JobApplication.objects.filter(job__company=company).count()
        shortlisted        = JobApplication.objects.filter(job__company=company, status='SHORTLISTED').count()

        return Response({
            'company_name':       company.company_name,
            'active_listings':    active_listings,
            'total_applications': total_applications,
            'shortlisted':        shortlisted,
        })
