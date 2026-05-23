import re

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import Student, Company, AdminProfile

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=User.Role.choices)

    name = serializers.CharField(max_length=100, write_only=True)
    department = serializers.CharField(required=False, allow_blank=True, write_only=True)
    desired_job_category = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, data):
        email = data["email"].lower().strip()
        password = data["password"]
        blocked_domains = ["example.com", "test.com", "fake.com"]

        email_domain = email.split("@")[-1]

        if email_domain in blocked_domains:
            raise serializers.ValidationError({
            "email": ["Please use a real email address."]
            })

        data["email"] = email

        if password != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": ["Passwords do not match."]
            })

        if len(password) < 8:
            raise serializers.ValidationError({
                "password": ["Password must be at least 8 characters long."]
            })

        if not re.search(r"[A-Za-z]", password):
            raise serializers.ValidationError({
                "password": ["Password must contain at least one letter."]
            })

        if not re.search(r"\d", password):
            raise serializers.ValidationError({
                "password": ["Password must contain at least one digit."]
            })

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=/\\[\]~`]", password):
            raise serializers.ValidationError({
                "password": ["Password must contain at least one special character."]
            })

        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError({
                "email": ["Email is already registered."]
            })

        return data

    def create(self, validated_data):
        role = validated_data["role"]
        name = validated_data["name"]

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            role=role,
            is_active=False,
            email_verified=False,
        )

        if role == "STUDENT":
            Student.objects.create(
                user=user,
                student_name=name,
                department=validated_data.get("department", ""),
                desired_job_category=validated_data.get("desired_job_category", ""),
            )

        elif role == "COMPANY":
            Company.objects.create(
                user=user,
                company_name=name,
            )

        elif role == "ADMIN":
            AdminProfile.objects.create(
                user=user,
                admin_name=name,
            )

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        verification_link = (
            f"{settings.FRONTEND_URL}/verify-email?uid={uid}&token={token}"
        )

        send_mail(
            subject="Verify your MomentumQuest account",
            message=(
                f"Hi {name},\n\n"
                f"Thank you for registering with MomentumQuest.\n\n"
                f"Please click the link below to verify your email:\n"
                f"{verification_link}\n\n"
                f"If you did not create this account, you can ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()

    def save(self):
        email = self.validated_data["email"]
        user = User.objects.filter(email=email).first()

        if not user:
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

        send_mail(
            subject="Reset your MomentumQuest password",
            message=(
                "Hi,\n\n"
                "We received a request to reset your MomentumQuest password.\n\n"
                "Click the link below to set a new password:\n"
                f"{reset_link}\n\n"
                "If you did not request this, you can ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": ["Passwords do not match."]
            })

        password = data["password"]

        if not re.search(r"[A-Za-z]", password):
            raise serializers.ValidationError({
                "password": ["Password must contain at least one letter."]
            })

        if not re.search(r"\d", password):
            raise serializers.ValidationError({
                "password": ["Password must contain at least one digit."]
            })

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=/\\[\]~`]", password):
            raise serializers.ValidationError({
                "password": ["Password must contain at least one special character."]
            })

        try:
            user_id = force_str(urlsafe_base64_decode(data["uid"]))
            user = User.objects.get(pk=user_id)
        except Exception:
            raise serializers.ValidationError({
                "detail": ["Invalid password reset link."]
            })

        if not default_token_generator.check_token(user, data["token"]):
            raise serializers.ValidationError({
                "detail": ["Password reset link is invalid or expired."]
            })

        data["user"] = user
        return data

    def save(self):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["password"])
        user.save(update_fields=["password"])
        return user
