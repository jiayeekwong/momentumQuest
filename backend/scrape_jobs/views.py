from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, filters, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminUserRole, IsStudent

from dashboard.views import MIN_LISTINGS_FOR_TARGET
from job_listings.models import JobListing, SavedJob, ScrapeLog
from .models import (
    JobCategory, JobTitle, MarketRole, Skill,
)
from .serializers import (
    ScrapedJobListSerializer,
    ScrapedJobDetailSerializer,
    JobCategorySerializer,
    JobTitleSerializer,
    ScrapeLogSerializer,
)

#: Ceiling on ?top= for the demand endpoint. High enough that no honest caller
#: meets it -- the ranking is a dashboard panel, not an export -- and low
#: enough that the annotate-and-slice cannot be asked to rank the whole
#: catalogue by an anonymous request.
MAX_DEMAND_ROWS = 200


def saved_job_ids_for(request):
    """The listing ids this student has bookmarked, as a set.

    One query for the whole page rather than one per card. Returns an empty
    set for anonymous visitors and for company accounts, which have no
    shortlist.
    """
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and hasattr(user, "student_profile")):
        return set()
    from job_listings.models import SavedJob
    return set(SavedJob.objects
               .filter(student=user.student_profile)
               .values_list("job_id", flat=True))


class ScrapedJobListView(generics.ListAPIView):
    """
    GET /api/jobs/scraped/
    List scraped jobs. Students see these with a "View on JobStreet" redirect.

    Query params:
      ?search=     — searches title, company, location, description
      ?category=   — filter by job category name
      ?job_type=   — filter by job type (Full-time, Contract, etc.)
      ?location=   — filter by location string
      ?saved=true  — only listings this student has bookmarked
      ?market_role= — filter to one Market Role
      ?broad_area= — filter to one Broad Area
      ?ordering=   — e.g. -scraped_time, salary_min
      ?include_expired=true — also return lapsed listings (default: active only)

    Lapsed listings are hidden by default: the source portal drops a posting
    after ~30 days, so an expired one sends the student to a dead page. They
    stay in the database because the demand analytics are built from history.
    """
    serializer_class = ScrapedJobListSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["job_title", "company_name", "location", "description"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["saved_job_ids"] = saved_job_ids_for(self.request)
        return context
    ordering_fields = ["posted_time", "posted_date", "salary_min", "salary_max"]
    ordering = ["-posted_time"]

    def get_queryset(self):
        qs = (
            JobListing.objects.filter(source_type="SCRAPED")
            .select_related("category")
            .prefetch_related("job_skills__skill")
        )
        if self.request.query_params.get("include_expired") != "true":
            qs = qs.filter(status=JobListing.Status.ACTIVE)

        category = self.request.query_params.get("category")
        job_type = self.request.query_params.get("job_type")
        location = self.request.query_params.get("location")
        broad_area = self.request.query_params.get("broad_area")
        market_role = self.request.query_params.get("market_role")

        if category:
            qs = qs.filter(category__category_name__icontains=category)
        if job_type:
            qs = qs.filter(job_type__icontains=job_type)
        if location:
            qs = qs.filter(location__icontains=location)
        if self.request.query_params.get("saved") == "true":
            qs = qs.filter(id__in=saved_job_ids_for(self.request))
        if broad_area:
            qs = qs.filter(market_role__broad_area__iexact=broad_area)
        if market_role:
            qs = qs.filter(market_role__name__iexact=market_role)

        return qs


class ScrapedJobDetailView(generics.RetrieveAPIView):
    """
    GET /api/jobs/scraped/<id>/
    Full detail including description. source_url is the redirect link to JobStreet.
    """
    queryset = (
        JobListing.objects.filter(source_type="SCRAPED")
        .select_related("category")
        .prefetch_related("job_skills__skill")
    )
    serializer_class = ScrapedJobDetailSerializer
    permission_classes = [AllowAny]


@api_view(["GET"])
def job_categories_view(request):
    """
    GET /api/jobs/categories/
    All job categories with job counts — used for trend visualisation chart.
    """
    categories = (
        JobCategory.objects
        .annotate(job_count=Count(
            "job_listings",
            filter=Q(job_listings__source_type="SCRAPED"),
        ))
        .filter(job_count__gt=0)
        .order_by("-job_count")
    )
    return Response(JobCategorySerializer(categories, many=True).data)


@api_view(["GET"])
def job_titles_view(request):
    """
    GET /api/scrape-jobs/job-titles/
    Normalised job titles students can pick as a target (UC signup/profile).

    Query params:
      ?category=  — filter by job category name
    """
    qs = JobTitle.objects.select_related("category", "market_role")
    category = request.query_params.get("category")
    if category:
        qs = qs.filter(category__category_name__icontains=category)
    return Response(JobTitleSerializer(qs, many=True).data)


@api_view(["GET"])
def skills_view(request):
    """
    GET /api/scrape-jobs/skills/?search=<text>
    The canonical skill vocabulary, for pickers that must write a Skill FK
    (certificate upload) rather than invent a free-text skill name.
    """
    # Retired skills and ones still awaiting a reviewer are not part of the
    # vocabulary yet. Offering them in the certificate picker let a student
    # attach evidence to a skill the catalogue does not stand behind.
    skills = Skill.objects.selectable().order_by("skill_category", "skill_name")
    search = (request.query_params.get("search") or "").strip()
    if search:
        skills = skills.filter(skill_name__icontains=search)
    return Response([
        {"id": skill.id, "skill_name": skill.skill_name,
         "skill_category": skill.skill_category}
        for skill in skills
    ])


@api_view(["GET"])
def skill_demand_view(request):
    """
    GET /api/jobs/skills/demand/
    Top skills ranked by demand across scraped jobs.
    Used for skill gap analysis — shows what the market wants.

    Query params:
      ?top=20       — how many skills to return (default 20)
      ?category=    — filter to a specific job category
      ?market_role= — filter to a specific Market Role
    """
    # A bad ?top= is the caller's mistake, so it gets a 400 naming the
    # parameter. int() on "abc" raised ValueError straight out of the view and
    # became a 500, which reads as a server fault and pages whoever is on call
    # for someone else's typo.
    raw_top = request.query_params.get("top", 20)
    try:
        top = int(raw_top)
    except (TypeError, ValueError):
        return Response({"top": [f"Not a whole number: {raw_top!r}"]},
                        status=status.HTTP_400_BAD_REQUEST)
    # Upper bound as well as lower: the annotate-and-slice below is not free,
    # and ?top=1000000 is a request to build the whole catalogue for one page.
    if top < 1 or top > MAX_DEMAND_ROWS:
        return Response(
            {"top": [f"Must be between 1 and {MAX_DEMAND_ROWS}."]},
            status=status.HTTP_400_BAD_REQUEST)

    category = request.query_params.get("category")
    market_role = request.query_params.get("market_role")

    # Every condition goes inside the aggregate, and the count is distinct.
    #
    # Filtering the queryset on job_skills *after* annotating over job_skills
    # made Django join that relation a second time, so the count became the
    # size of the cross product: "Communication" under Data Analyst returned
    # 26,455 rather than 55. .distinct() could not repair it -- it de-duplicates
    # the rows, not the rows the aggregate has already counted.
    demand_filter = Q(job_skills__job__source_type="SCRAPED")
    if category:
        demand_filter &= Q(
            job_skills__job__category__category_name__icontains=category)
    if market_role:
        demand_filter &= Q(job_skills__job__market_role__name__iexact=market_role)

    qs = (
        Skill.objects
        .annotate(demand_count=Count("job_skills", filter=demand_filter,
                                     distinct=True))
        .filter(demand_count__gt=0)
        .order_by("-demand_count")[:top]
    )

    return Response([
        {
            "skill": s.skill_name,
            "category": s.skill_category,
            "demand_count": s.demand_count,
        }
        for s in qs
    ])



@api_view(["GET"])
@permission_classes([IsAdminUserRole])
def scrape_logs_view(request):
    """
    GET /api/jobs/scrape-logs/
    Last 20 scrape run records — shows SUCCESS / BLOCKED / PARTIAL / FAILED status.
    Used by admin to monitor scraper health.

    Admin only. REST_FRAMEWORK sets no DEFAULT_PERMISSION_CLASSES, so DRF's own
    AllowAny applied and this was readable by anyone at all -- including the
    error_message field, which carries scraper internals and blocked-by-portal
    detail that has no reason to be public.
    """
    logs = ScrapeLog.objects.all()[:20]
    return Response(ScrapeLogSerializer(logs, many=True).data)


@api_view(["GET"])
def market_roles_view(request):
    """
    GET /api/scrape-jobs/market-roles/
    The Market Roles a student can target, grouped by Broad Area.

    A Market Role is a standardized career group derived from the job titles
    Malaysian ICT employers actually advertise. Raw and Normalized Job Titles
    are never offered here: "Senior Front-End Engineer (Remote)" is one
    employer\'s advert and "frontend engineer" is matching evidence, but
    "Frontend Developer" is the career.

    Broad Area is presentation only. It groups the list; it never decides
    which role an advert belongs to.

    A role the market cannot yet evidence is still returned, because a student
    is allowed to want it. Whether it can be *analysed* is the separate
    question ``analysable`` answers, using the same evidence floor the skill
    gap uses.
    """
    # Open adverts only, matching what the skill gap measures against and
    # what the jobs page lists. A picker promising "9 jobs" for a role the
    # analysis then reports as unanalysable is the same number meaning two
    # different things on two screens.
    counts = dict(
        JobListing.objects
        .filter(source_type="SCRAPED", status=JobListing.Status.ACTIVE,
                market_role__isnull=False)
        .values_list("market_role_id")
        .annotate(total=Count("id"))
    )

    areas = {}
    for role in MarketRole.objects.filter(is_active=True):
        bucket = areas.setdefault(role.broad_area or "Other", {
            "name": role.broad_area or "Other",
            "roles": [],
        })
        count = counts.get(role.id, 0)
        bucket["roles"].append({
            "id": role.id,
            "name": role.name,
            "broad_area": role.broad_area,
            "description": role.description,
            "advert_count": count,
            "analysable": count >= MIN_LISTINGS_FOR_TARGET,
        })

    results = list(areas.values())
    return Response({
        "evidence_floor": MIN_LISTINGS_FOR_TARGET,
        "total_roles": sum(len(area["roles"]) for area in results),
        "analysable_roles": sum(1 for area in results
                                for role in area["roles"] if role["analysable"]),
        "results": results,
    })


class SavedJobView(APIView):
    """
    POST   /api/jobs/scraped/<pk>/save/   — bookmark a listing
    DELETE /api/jobs/scraped/<pk>/save/   — remove the bookmark

    A private shortlist. Saving commits the student to nothing and is never
    disclosed to the employer, which is what makes it different from applying.

    Both verbs are idempotent: saving twice is the same as saving once, and
    un-saving something that was never saved is not an error. A bookmark
    button that fails on a double-click is worse than one that shrugs.
    """
    permission_classes = [IsStudent]

    def post(self, request, pk):
        listing = get_object_or_404(
            JobListing, pk=pk, source_type=JobListing.SourceType.SCRAPED)
        SavedJob.objects.get_or_create(
            student=request.user.student_profile, job=listing)
        return Response({"is_saved": True}, status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        SavedJob.objects.filter(
            student=request.user.student_profile, job_id=pk).delete()
        return Response({"is_saved": False}, status=status.HTTP_200_OK)
