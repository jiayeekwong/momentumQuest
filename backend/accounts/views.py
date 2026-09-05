from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from .permissions import IsStudent
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.mail import send_mail
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import RoleTerminologyFeedback, StudentSkill, UserConsent
from .departments import COURSE_DEPARTMENTS, DEPARTMENTS
from .privacy_notice import get_notice
from .withdrawal import WithdrawalError, restore_consent, withdraw_latest
from .serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    StudentSkillSerializer,
    UserConsentSerializer,
    set_student_target_roles,
)


class PrivacyNoticeCurrentView(APIView):
    """
    GET /api/auth/privacy-notice/current/

    Public by necessity: the notice has to be readable before an account
    exists, since acknowledging it is a precondition of creating one.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(get_notice())


class DepartmentListView(APIView):
    """
    GET /api/auth/departments/

    Public because the sign-up form needs it before an account exists. The
    lists used to be hardcoded separately in two frontend pages, which had
    already drifted; this is now the only source.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            "departments": DEPARTMENTS,
            "course_departments": COURSE_DEPARTMENTS,
        })


class MyConsentsView(generics.ListAPIView):
    """
    GET /api/auth/me/consents/

    A user's own consent history: what they agreed to, which notice version,
    and when. Scoped to request.user with no lookup parameter, so there is no
    way to ask for anybody else's.
    """
    serializer_class = UserConsentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserConsent.objects.filter(user=self.request.user)


class RestoreConsentView(APIView):
    """
    POST /api/auth/me/consents/restore/
    Body: {"consent_type": "DOCUMENT_VERIFICATION_CONSENT"}

    Gives a withdrawn consent again. Scoped to request.user, like withdrawal,
    so nobody can restore a consent on someone else's behalf -- "an
    administrator re-consented for you" is not something consent can mean.

    This is the path the withdrawal message names. Without it, withdrawing was
    a one-way door that permanently disabled document verification.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        consent_type = request.data.get("consent_type")
        if consent_type not in WithdrawConsentView.WITHDRAWABLE:
            return Response(
                {"consent_type": [
                    "Must be one of: "
                    + ", ".join(sorted(WithdrawConsentView.WITHDRAWABLE))]},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            consent = restore_consent(request.user, consent_type, request=request)
        except WithdrawalError as exc:
            return Response({"detail": str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "consent_type": consent.consent_type,
            "accepted_at": consent.accepted_at,
            "notice_version": consent.notice_version,
            # Said plainly, because the student may expect otherwise: the
            # documents and the skills they supported are gone, and giving
            # consent again does not bring back evidence nobody has reviewed
            # since.
            "detail": ("Document verification is enabled again. Skills removed "
                       "when you withdrew are not restored -- upload the "
                       "documents again to have them verified."),
        })


class WithdrawConsentView(APIView):
    """
    POST /api/auth/me/consents/withdraw/
    Body: {"consent_type": "DOCUMENT_VERIFICATION_CONSENT"}

    Withdraws the caller's own currently-active consent of that type. Scoped to
    request.user with no lookup parameter, so there is no way to withdraw
    anybody else's -- and no admin variant here, because "an administrator
    revoked your consent" is not a thing consent can mean.

    The consequences (skills recalculated, audit row written, the record kept)
    all live in accounts.withdrawal, so they cannot be forgotten by a caller.
    """
    permission_classes = [permissions.IsAuthenticated]

    # Only the consents a user can meaningfully turn off. The privacy-notice
    # acknowledgement is not among them: it records that they were shown the
    # notice, which stays true, and un-acknowledging it would mean holding an
    # account whose terms they had never seen.
    WITHDRAWABLE = {
        UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
        UserConsent.ConsentType.CV_PROCESSING_CONSENT,
    }

    def post(self, request):
        consent_type = request.data.get("consent_type")
        if consent_type not in self.WITHDRAWABLE:
            return Response(
                {"consent_type": [
                    "Must be one of: " + ", ".join(sorted(self.WITHDRAWABLE))]},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            consent, skills_removed = withdraw_latest(
                request.user, consent_type, actor=request.user, request=request)
        except WithdrawalError as exc:
            return Response({"detail": str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "consent_type": consent.consent_type,
            "withdrawn_at": consent.withdrawn_at,
            "notice_version": consent.notice_version,
            "skills_removed": skills_removed,
            "detail": (
                "Consent withdrawn. MomentumQuest will not verify new documents "
                "for you. Your account and your existing applications are "
                "unchanged."
            ),
        })


class RegisterView(generics.CreateAPIView):
    throttle_scope = "register"
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

class CustomTokenObtainPairView(TokenObtainPairView):
    throttle_scope = "login"
    serializer_class = CustomTokenObtainPairSerializer


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        data = {
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
        }

        if user.role == 'STUDENT' and hasattr(user, 'student_profile'):
            profile = user.student_profile
            data["student_name"] = profile.student_name
            data["department"] = profile.department
            data["matric_number"] = profile.matric_number
            # The Broad Area comes back with the name so a client can group
            # the student\'s targets without a second request. It is
            # presentation metadata only -- the target is the Market Role.
            data["target_roles"] = [
                {
                    "market_role": t.market_role.name,
                    "broad_area": t.market_role.broad_area,
                    "added_time": t.added_time,
                }
                for t in profile.target_roles.select_related("market_role")
            ]

        elif user.role == 'COMPANY' and hasattr(user, 'company_profile'):
            data["company_name"] = user.company_profile.company_name

        elif user.role == 'ADMIN' and hasattr(user, 'admin_profile'):
            data["admin_name"] = user.admin_profile.admin_name

        return Response(data)

    def patch(self, request):
        user = request.user

        if user.role == 'COMPANY' and hasattr(user, 'company_profile'):
            company_name = request.data.get('company_name', '').strip()
            if not company_name:
                return Response({'company_name': ['This field may not be blank.']},
                                status=status.HTTP_400_BAD_REQUEST)
            user.company_profile.company_name = company_name
            user.company_profile.save(update_fields=['company_name'])

        elif user.role == 'STUDENT' and hasattr(user, 'student_profile'):
            profile = user.student_profile
            if 'student_name' in request.data:
                profile.student_name = request.data['student_name'].strip() or profile.student_name
            if 'department' in request.data:
                department = request.data['department'] or ''
                if department and department not in DEPARTMENTS:
                    return Response(
                        {'department': [f"'{department}' is not a recognised department."]},
                        status=status.HTTP_400_BAD_REQUEST)
                profile.department = department
            if 'matric_number' in request.data:
                profile.matric_number = str(request.data['matric_number']).strip()
            profile.save()
            # target_roles is the only target a user may set. The MASCO
            # occupation is derived from it inside set_student_target_roles;
            # accepting target_occupation_ids here let the dashboard overwrite
            # the occupation independently, so the trend chart and the skill
            # gap could describe different careers.
            if 'target_roles' in request.data:
                set_student_target_roles(profile, request.data['target_roles'])

        return self.get(request)
    
User = get_user_model()


class VerifyEmailView(APIView):
    throttle_scope = "verify_email"
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")

        if not uid or not token:
            return Response(
                {"detail": "Invalid verification link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except Exception:
            return Response(
                {"detail": "Invalid verification link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"detail": "Verification link is invalid or expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.email_verified and user.is_active:
            return Response({
                "detail": "Email is already verified. You can login."
            })

        user.is_active = True
        user.email_verified = True
        user.save(update_fields=["is_active", "email_verified"])

        return Response({
            "detail": "Email verified successfully. You can now login."
        })


class StudentSkillListView(generics.ListAPIView):
    """
    GET /api/accounts/student/skills/
    Returns the logged-in student's skills â€” used by the job marketplace
    to calculate match scores client-side.
    """
    serializer_class = StudentSkillSerializer
    permission_classes = [IsStudent]

    def get_queryset(self):
        return StudentSkill.objects.filter(
            student=self.request.user.student_profile
        ).select_related('skill')


class EmailChangeRequestView(APIView):
    throttle_scope = "password_reset"
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        new_email = request.data.get('new_email', '').lower().strip()
        password  = request.data.get('password', '')

        if not new_email or not password:
            return Response({'detail': 'New email and current password are required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if not request.user.check_password(password):
            return Response({'password': ['Incorrect password.']},
                            status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=new_email).exists():
            return Response({'new_email': ['This email address is already in use.']},
                            status=status.HTTP_400_BAD_REQUEST)

        token = signing.dumps(
            {'user_id': request.user.id, 'new_email': new_email},
            salt='mq-email-change',
        )

        confirm_link = f"{settings.FRONTEND_URL}/confirm-email-change?token={token}"

        send_mail(
            subject="Confirm your email change — MomentumQuest",
            message=(
                f"Hi,\n\n"
                f"We received a request to change your MomentumQuest email address.\n\n"
                f"Click the link below to confirm your new email address:\n"
                f"{confirm_link}\n\n"
                f"This link will expire in 15 minutes.\n\n"
                f"If you did not request this change, you can ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[new_email],
            fail_silently=False,
        )

        return Response({'detail': f'A verification link has been sent to {new_email}. Click it to confirm the change.'})


class EmailChangeConfirmView(APIView):
    throttle_scope = "token_confirm"
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('token', '')

        try:
            data = signing.loads(token, salt='mq-email-change', max_age=900)
        except signing.SignatureExpired:
            return Response({'detail': 'This link has expired. Please request a new email change.'},
                            status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({'detail': 'Invalid confirmation link.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=data['user_id'])
        except User.DoesNotExist:
            return Response({'detail': 'Invalid confirmation link.'},
                            status=status.HTTP_400_BAD_REQUEST)

        new_email = data['new_email']

        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            return Response({'detail': 'This email is already taken by another account.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user.email = new_email
        user.save(update_fields=['email'])

        return Response({'detail': 'Email updated successfully. Please log in again with your new email.'})


class PasswordResetRequestView(APIView):
    throttle_scope = "password_reset"
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "detail": "If this email is registered, a password reset link will be sent."
        })


class PasswordResetConfirmView(APIView):
    throttle_scope = "token_confirm"
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "detail": "Password reset successfully. You can now login."
        })


class PasswordChangeView(APIView):
    throttle_scope = "password_reset"
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .serializers import validate_strong_password
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from django.contrib.auth.hashers import make_password

        current_password = request.data.get('current_password', '')
        new_password     = request.data.get('new_password', '')
        confirm_password = request.data.get('confirm_password', '')

        if not current_password or not new_password or not confirm_password:
            return Response(
                {'detail': 'All fields are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(current_password):
            return Response(
                {'current_password': ['Incorrect password.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_password != confirm_password:
            return Response(
                {'confirm_password': ['Passwords do not match.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_strong_password(new_password)
        except DRFValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        token = signing.dumps(
            {'user_id': request.user.id, 'new_password_hash': make_password(new_password)},
            salt='mq-password-change',
        )

        confirm_link = f"{settings.FRONTEND_URL}/confirm-password-change?token={token}"

        send_mail(
            subject="Confirm your password change — MomentumQuest",
            message=(
                f"Hi,\n\n"
                f"We received a request to change your MomentumQuest password.\n\n"
                f"Click the link below to confirm the change:\n"
                f"{confirm_link}\n\n"
                f"This link will expire in 15 minutes.\n\n"
                f"If you did not request this change, you can ignore this email — your password will not be changed."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[request.user.email],
            fail_silently=False,
        )

        return Response({'detail': f'A verification link has been sent to {request.user.email}. Click it to confirm the password change.'})


class PasswordChangeConfirmView(APIView):
    throttle_scope = "token_confirm"
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('token', '')

        try:
            data = signing.loads(token, salt='mq-password-change', max_age=900)
        except signing.SignatureExpired:
            return Response(
                {'detail': 'This link has expired. Please request a new password change.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except signing.BadSignature:
            return Response(
                {'detail': 'Invalid confirmation link.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(pk=data['user_id'])
        except User.DoesNotExist:
            return Response(
                {'detail': 'Invalid confirmation link.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.password = data['new_password_hash']
        user.save(update_fields=['password'])

        return Response({'detail': 'Password changed successfully. Please log in again with your new password.'})


class RoleTerminologyFeedbackView(APIView):
    """
    POST /api/auth/student/role-feedback/
    Records the wording a student looked for when no Market Role matched.

    Deliberately writes nothing else. It does not create a role, does not set
    a target, and returns no suggestion -- an "Other" role would have no
    adverts and no skills behind it, so the vocabulary gap is captured as data
    rather than papered over. The reply just acknowledges.

    This is the evidence for the next review pass: a search term seen often
    is either a missing reviewed alias or a Market Role worth proposing.
    """
    permission_classes = [IsStudent]

    def post(self, request):
        text = str(request.data.get('searched_text', '')).strip()
        if not text:
            return Response({'detail': 'Tell us what you were looking for.'},
                            status=status.HTTP_400_BAD_REQUEST)

        RoleTerminologyFeedback.objects.create(
            student=request.user.student_profile,
            searched_text=text[:200],
            context_broad_area=str(
                request.data.get('context_broad_area') or '')[:80],
        )
        return Response({'recorded': True}, status=status.HTTP_201_CREATED)
