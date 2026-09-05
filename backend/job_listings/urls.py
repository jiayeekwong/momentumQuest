from django.urls import path

from .views import (
    CompanyApplicationListView,
    CompanyApplicationStatusView,
    CompanyJobDetailView,
    CompanyJobListingView,
    CVParseView,
    PublicJobListingView,
    SkillExtractionView,
    StudentJobApplicationView,
)

urlpatterns = [
    path('jobs/',                          CompanyJobListingView.as_view()),
    path('jobs/<int:pk>/',                 CompanyJobDetailView.as_view()),
    path('skills/extract/',                SkillExtractionView.as_view()),   # Suggest skills from a draft description
    path('cv/parse/',                      CVParseView.as_view()),                  # Parse a CV, then delete it
    path('applications/',                  StudentJobApplicationView.as_view()),  # Student POST to apply
    path('company/applications/',          CompanyApplicationListView.as_view()),  # Company GET applications
    path('applications/<int:pk>/status/',  CompanyApplicationStatusView.as_view()),
    path('public/',                        PublicJobListingView.as_view()),
]
