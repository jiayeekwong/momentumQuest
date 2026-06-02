from django.urls import path

from .views import (
    CompanyApplicationListView,
    CompanyApplicationStatusView,
    CompanyJobDetailView,
    CompanyJobListingView,
    PublicJobListingView,
    StudentJobApplicationView,
)

urlpatterns = [
    path('jobs/',                          CompanyJobListingView.as_view()),
    path('jobs/<int:pk>/',                 CompanyJobDetailView.as_view()),
    path('applications/',                  StudentJobApplicationView.as_view()),  # Student POST to apply
    path('company/applications/',          CompanyApplicationListView.as_view()),  # Company GET applications
    path('applications/<int:pk>/status/',  CompanyApplicationStatusView.as_view()),
    path('public/',                        PublicJobListingView.as_view()),
]
