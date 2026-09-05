from django.urls import path

from . import views

urlpatterns = [
    path("",                               views.LearningResourceListView.as_view(), name="learning-resources"),
    path("courses/",                       views.CourseListView.as_view(),            name="course-list"),
    path("courses/<int:pk>/",              views.CourseDetailView.as_view(),          name="course-detail"),
    path("certificates/",                  views.CertificateListCreateView.as_view(), name="certificate-list"),
    path("certificates/<int:pk>/endorse/", views.CertificateEndorseView.as_view(),    name="certificate-endorse"),
    path("certificates/<int:pk>/file/",    views.CertificateFileView.as_view(),       name="certificate-file"),
    path("certificates/<int:pk>/",         views.CertificateDetailView.as_view(),     name="certificate-detail"),
    # There is no transcript file route and no admin review queue: the PDF is
    # deleted as soon as its subjects are read, so there is nothing to serve
    # and nothing to review.
    path("skill-validation/transcripts/",             views.TranscriptListCreateView.as_view(), name="transcript-list"),
    path("training/",                          views.CompanyTrainingView.as_view(),      name="training-list"),
    path("training/upload/",                   views.TrainingFileUploadView.as_view(),   name="training-upload"),
    path("training/admin/",                    views.AdminTrainingListView.as_view(),    name="training-admin-list"),
    path("training/admin/<int:pk>/review/",    views.AdminTrainingReviewView.as_view(),  name="training-admin-review"),
    path("training/approved/",                 views.ApprovedTrainingListView.as_view(), name="training-approved"),
]
