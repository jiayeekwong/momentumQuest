from django.urls import path

from . import views

urlpatterns = [
    path("scraped/",          views.ScrapedJobListView.as_view(),      name="scraped-job-list"),
    path("scraped/<int:pk>/", views.ScrapedJobDetailView.as_view(),     name="scraped-job-detail"),
    path("categories/",       views.job_categories_view,                name="job-categories"),
    path("skills/demand/",    views.skill_demand_view,                  name="skill-demand"),
    path("resources/",        views.LearningResourceListView.as_view(), name="learning-resources"),
    path("scrape-logs/",      views.scrape_logs_view,                   name="scrape-logs"),
]
