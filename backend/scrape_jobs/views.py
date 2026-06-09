from django.db.models import Count, Q
from rest_framework import generics, filters
from rest_framework.decorators import api_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from job_listings.models import JobListing, ScrapeLog
from .models import JobCategory, JobTitle, Skill
from .serializers import (
    ScrapedJobListSerializer,
    ScrapedJobDetailSerializer,
    JobCategorySerializer,
    JobTitleSerializer,
    ScrapeLogSerializer,
)


class ScrapedJobListView(generics.ListAPIView):
    """
    GET /api/jobs/scraped/
    List scraped jobs. Students see these with a "View on JobStreet" redirect.

    Query params:
      ?search=     — searches title, company, location, description
      ?category=   — filter by job category name
      ?job_type=   — filter by job type (Full-time, Contract, etc.)
      ?location=   — filter by location string
      ?ordering=   — e.g. -scraped_time, salary_min
    """
    serializer_class = ScrapedJobListSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["job_title", "company_name", "location", "description"]
    ordering_fields = ["posted_time", "posted_date", "salary_min", "salary_max"]
    ordering = ["-posted_time"]

    def get_queryset(self):
        qs = (
            JobListing.objects.filter(source_type="SCRAPED")
            .select_related("category")
            .prefetch_related("job_skills__skill")
        )
        category = self.request.query_params.get("category")
        job_type = self.request.query_params.get("job_type")
        location = self.request.query_params.get("location")

        if category:
            qs = qs.filter(category__category_name__icontains=category)
        if job_type:
            qs = qs.filter(job_type__icontains=job_type)
        if location:
            qs = qs.filter(location__icontains=location)

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
    qs = JobTitle.objects.select_related("category").all()
    category = request.query_params.get("category")
    if category:
        qs = qs.filter(category__category_name__icontains=category)
    return Response(JobTitleSerializer(qs, many=True).data)


@api_view(["GET"])
def skill_demand_view(request):
    """
    GET /api/jobs/skills/demand/
    Top skills ranked by demand across scraped jobs.
    Used for skill gap analysis — shows what the market wants.

    Query params:
      ?top=20       — how many skills to return (default 20)
      ?category=    — filter to a specific job category
    """
    top = int(request.query_params.get("top", 20))
    category = request.query_params.get("category")

    qs = Skill.objects.annotate(
        demand_count=Count(
            "job_skills",
            filter=Q(job_skills__job__source_type="SCRAPED"),
        )
    ).filter(demand_count__gt=0)

    if category:
        qs = qs.filter(
            job_skills__job__source_type="SCRAPED",
            job_skills__job__category__category_name__icontains=category,
        ).distinct()

    qs = qs.order_by("-demand_count")[:top]

    return Response([
        {
            "skill": s.skill_name,
            "category": s.skill_category,
            "demand_count": s.demand_count,
        }
        for s in qs
    ])



@api_view(["GET"])
def scrape_logs_view(request):
    """
    GET /api/jobs/scrape-logs/
    Last 20 scrape run records — shows SUCCESS / BLOCKED / PARTIAL / FAILED status.
    Used by admin to monitor scraper health.
    """
    logs = ScrapeLog.objects.all()[:20]
    return Response(ScrapeLogSerializer(logs, many=True).data)
