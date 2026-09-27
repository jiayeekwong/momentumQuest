from django.urls import path

from .views import (
    AnnouncementListView,
    AnnouncementCreateView,
    AnnouncementAttachmentView,
    AnnouncementDeleteView,
    AnnouncementFileUploadView,
    StudentDashboardView,
    SkillResourcesView,
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
    # No trailing slash, unlike the rest of this module: the value is a
    # file, and a URL ending in its extension is what an <img> tag, a
    # download and anything sniffing the type all expect.
    path('announcements/attachment/<str:name>',
         AnnouncementAttachmentView.as_view(), name='announcement-attachment'),
    path('announcements/<int:pk>/', AnnouncementDeleteView.as_view()),
    path('student/',                StudentDashboardView.as_view()),
    path('skill-gap/',              StudentSkillGapView.as_view(),   name='student-skill-gap'),
    path('skill-resources/',        SkillResourcesView.as_view(),    name='skill-resources'),
    path('skill-gap/market-roles/', MarketRoleScopeView.as_view(),   name='skill-gap-market-roles'),
    path('market-role/',            MarketRoleProfileView.as_view(), name='market-role-profile'),
    path('market-demand/',          MarketDemandView.as_view(),    name='student-market-demand'),
    path('admin/',                  AdminDashboardView.as_view()),
    path('company/',                CompanyDashboardView.as_view()),
]
