from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from .permissions import IsCompany, IsStudent, IsAdminUserRole
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import status

from .serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


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

        if default_token_generator.check_token(user, token):
            user.is_active = True
            user.email_verified = True
            user.save(update_fields=["is_active", "email_verified"])

            return Response({
                "detail": "Email verified successfully. You can now login."
            })

        return Response(
            {"detail": "Verification link is invalid or expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )


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
