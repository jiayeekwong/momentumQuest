from django.urls import path

from . import views

urlpatterns = [
    path("scraped/",          views.ScrapedJobListView.as_view(),      name="scraped-job-list"),
    path("scraped/<int:pk>/", views.ScrapedJobDetailView.as_view(),     name="scraped-job-detail"),
    path("scraped/<int:pk>/save/", views.SavedJobView.as_view(),        name="scraped-job-save"),
    path("categories/",       views.job_categories_view,                name="job-categories"),
    path("job-titles/",       views.job_titles_view,                    name="job-titles"),
    path("market-roles/",     views.market_roles_view,                  name="market-roles"),
    path("skills/",           views.skills_view,                        name="skill-list"),
    path("skills/demand/",    views.skill_demand_view,                  name="skill-demand"),
    path("scrape-logs/",      views.scrape_logs_view,                   name="scrape-logs"),
]
