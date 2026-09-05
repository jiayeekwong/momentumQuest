from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    CustomTokenObtainPairView,
    DepartmentListView,
    EmailChangeConfirmView,
    EmailChangeRequestView,
    MyConsentsView,
    RestoreConsentView,
    WithdrawConsentView,
    PasswordChangeConfirmView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PrivacyNoticeCurrentView,
    ProfileView,
    RegisterView,
    RoleTerminologyFeedbackView,
    StudentSkillListView,
    VerifyEmailView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', ProfileView.as_view(), name='profile'),

    path('privacy-notice/current/', PrivacyNoticeCurrentView.as_view(), name='privacy_notice_current'),
    path('me/consents/', MyConsentsView.as_view(), name='my_consents'),
    path('me/consents/withdraw/', WithdrawConsentView.as_view(), name='withdraw_consent'),
    path('me/consents/restore/', RestoreConsentView.as_view(), name='restore_consent'),
    path('departments/', DepartmentListView.as_view(), name='departments'),

    path('verify-email/', VerifyEmailView.as_view(), name='verify_email'),
    path('student/skills/', StudentSkillListView.as_view(), name='student_skills'),
    path('student/role-feedback/', RoleTerminologyFeedbackView.as_view(), name='role_terminology_feedback'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password_reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('email-change/', EmailChangeRequestView.as_view(), name='email_change'),
    path('email-change/confirm/', EmailChangeConfirmView.as_view(), name='email_change_confirm'),
    path('password-change/', PasswordChangeView.as_view(), name='password_change'),
    path('password-change/confirm/', PasswordChangeConfirmView.as_view(), name='password_change_confirm'),
]
