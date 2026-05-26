from django.urls import path

from . import views

urlpatterns = [
    path("",                               views.LearningResourceListView.as_view(), name="learning-resources"),
    path("courses/",                       views.CourseListView.as_view(),            name="course-list"),
    path("courses/<int:pk>/",              views.CourseDetailView.as_view(),          name="course-detail"),
    path("certificates/",                  views.CertificateListCreateView.as_view(), name="certificate-list"),
    path("certificates/<int:pk>/endorse/", views.CertificateEndorseView.as_view(),    name="certificate-endorse"),
]
