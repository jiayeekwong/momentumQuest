from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/',      include('accounts.urls')),
    path('api/scrape-jobs/',   include('scrape_jobs.urls')),
    path('api/resources/',     include('resources.urls')),
    path('api/dashboard/',     include('dashboard.urls')),
    path('api/job-listings/',  include('job_listings.urls')),
]