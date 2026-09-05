from django.urls import path

from .views import (
    AnnouncementListView,
    AnnouncementCreateView,
    AnnouncementDeleteView,
    AnnouncementFileUploadView,
    StudentDashboardView,
    StudentSkillGapView,
    MarketRoleScopeView,
    MarketRoleProfileView,
    MarketDemandView,
    AdminDashboardView,
    CompanyDashboardView,
    StudentNotificationsView,
)

urlpatterns = [
    path('notifications/',          StudentNotificationsView.as_view()),
    path('announcements/',          AnnouncementListView.as_view()),
    path('announcements/create/',   AnnouncementCreateView.as_view()),
    path('announcements/upload/',   AnnouncementFileUploadView.as_view()),
    path('announcements/<int:pk>/', AnnouncementDeleteView.as_view()),
    path('student/',                StudentDashboardView.as_view()),
    path('skill-gap/',              StudentSkillGapView.as_view(),   name='student-skill-gap'),
    path('skill-gap/market-roles/', MarketRoleScopeView.as_view(),   name='skill-gap-market-roles'),
    path('market-role/',            MarketRoleProfileView.as_view(), name='market-role-profile'),
    path('market-demand/',          MarketDemandView.as_view(),    name='student-market-demand'),
    path('admin/',                  AdminDashboardView.as_view()),
    path('company/',                CompanyDashboardView.as_view()),
]
