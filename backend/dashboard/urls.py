from django.urls import path

from .views import (
    AnnouncementListView,
    AnnouncementCreateView,
    AnnouncementDeleteView,
    AnnouncementFileUploadView,
    StudentDashboardView,
    AdminDashboardView,
    CompanyDashboardView,
)

urlpatterns = [
    path('announcements/',          AnnouncementListView.as_view()),
    path('announcements/create/',   AnnouncementCreateView.as_view()),
    path('announcements/upload/',   AnnouncementFileUploadView.as_view()),
    path('announcements/<int:pk>/', AnnouncementDeleteView.as_view()),
    path('student/',                StudentDashboardView.as_view()),
    path('admin/',                  AdminDashboardView.as_view()),
    path('company/',                CompanyDashboardView.as_view()),
]
