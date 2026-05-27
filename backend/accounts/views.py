from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from .permissions import IsCompany, IsStudent, IsAdminUserRole
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.mail import send_mail
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import StudentSkill
from .serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    StudentSkillSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

class CustomTokenObtainPairView(TokenObtainPairView):
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
            data["student_name"] = user.student_profile.student_name
            data["department"] = user.student_profile.department
            data["desired_job_category"] = user.student_profile.desired_job_category

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
                profile.department = request.data['department']
            if 'desired_job_category' in request.data:
                profile.desired_job_category = request.data['desired_job_category']
            profile.save()

        return self.get(request)
    
# Temporary test views to verify role-based permissions, can be removed later
class StudentOnlyTestView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        return Response({
            "message": "You are Student, only student users can access this."
        })


class CompanyOnlyTestView(APIView):
    permission_classes = [IsCompany]

    def get(self, request):
        return Response({
            "message": "You are Company, only company users can access this."
        })


class AdminOnlyTestView(APIView):
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        return Response({
            "message": "You are Admin, only admin users can access this."
        })

User = get_user_model()


class VerifyEmailView(APIView):
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
    Returns the logged-in student's skills — used by the job marketplace
    to calculate match scores client-side.
    """
    serializer_class = StudentSkillSerializer
    permission_classes = [IsStudent]

    def get_queryset(self):
        return StudentSkill.objects.filter(
            student=self.request.user.student_profile
        ).select_related('skill')


class EmailChangeRequestView(APIView):
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
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "detail": "If this email is registered, a password reset link will be sent."
        })


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "detail": "Password reset successfully. You can now login."
        })


class PasswordChangeView(APIView):
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
