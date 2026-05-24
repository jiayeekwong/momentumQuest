import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AdminProfile, Company, Student


User = get_user_model()


# ============================================================
# Constants
# ============================================================

BLOCKED_EMAIL_DOMAINS = ["example.com", "test.com", "fake.com"]

SPECIAL_CHARACTER_PATTERN = r"[!@#$%^&*(),.?\":{}|<>_\-+=/\\[\]~`]"


# ============================================================
# Validation helper functions
# ============================================================

def validate_real_email_domain(email):
    """
    Block fake/test email domains.

    serializers.EmailField() already checks if the email format is valid.
    This function only blocks obvious test domains.
    """
    email_domain = email.split("@")[-1].lower()

    if email_domain in BLOCKED_EMAIL_DOMAINS:
        raise serializers.ValidationError({
            "email": ["Please use a real email address."]
        })


def validate_strong_password(password):
    """
    Password rules:
    - at least 8 characters
    - at least one letter
    - at least one digit
    - at least one special character
    """
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

    if not re.search(SPECIAL_CHARACTER_PATTERN, password):
        raise serializers.ValidationError({
            "password": ["Password must contain at least one special character."]
        })


def get_user_from_uid(uid):
    """
    Decode uid from verification/reset-password URL.
    Return the user if valid, otherwise return None.
    """
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        return User.objects.get(pk=user_id)

    except Exception:
        return None


# ============================================================
# Email helper functions
# ============================================================

def send_verification_email(user, name):
    """
    Send email verification link.

    Used when:
    - a new user registers
    - an existing unverified user registers again
    """
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
            f"This link will expire after 15 minutes.\n\n"
            f"If you did not create this account, you can ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def send_password_reset_email(user):
    """
    Send password reset link.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    reset_link = (
        f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    )

    send_mail(
        subject="Reset your MomentumQuest password",
        message=(
            f"Hi,\n\n"
            f"We received a request to reset your MomentumQuest password.\n\n"
            f"Please click the link below to reset your password:\n"
            f"{reset_link}\n\n"
            f"This link will expire after 15 minutes.\n\n"
            f"If you did not request this, you can ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


# ============================================================
# Register serializer
# ============================================================

class RegisterSerializer(serializers.Serializer):
    """
    Handles user registration.

    Important:
    - User is created as inactive first.
    - User can only login after email verification.
    - If an unverified user registers again, we reuse the same user record
      and resend a new verification email.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=User.Role.choices)

    name = serializers.CharField(max_length=100, write_only=True)

    department = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
    )

    desired_job_category = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
    )

    def validate(self, data):
        email = data["email"].lower().strip()
        password = data["password"]

        data["email"] = email

        validate_real_email_domain(email)

        if password != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": ["Passwords do not match."]
            })

        validate_strong_password(password)

        existing_user = User.objects.filter(email=email).first()

        if existing_user:
            if existing_user.email_verified and existing_user.is_active:
                raise serializers.ValidationError({
                    "email": ["Email is already registered. Please login instead."]
                })

            self.existing_unverified_user = existing_user

        return data

    def create(self, validated_data):
        role = validated_data["role"]
        name = validated_data["name"]

        existing_user = getattr(self, "existing_unverified_user", None)

        if existing_user:
            user = self.update_existing_unverified_user(
                existing_user,
                validated_data,
            )

        else:
            user = self.create_new_inactive_user(validated_data)

        self.create_role_profile(user, role, name, validated_data)

        send_verification_email(user, name)

        return user

    def create_new_inactive_user(self, validated_data):
        """
        Create a new inactive user.
        The account becomes active only after email verification.
        """
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            role=validated_data["role"],
            is_active=False,
            email_verified=False,
        )

        return user

    def update_existing_unverified_user(self, user, validated_data):
        """
        Reuse an existing unverified account.

        This solves the issue where a user registers but never clicks
        the verification link, then tries to register again with the same email.
        """
        user.role = validated_data["role"]
        user.is_active = False
        user.email_verified = False
        user.set_password(validated_data["password"])

        user.save(update_fields=[
            "role",
            "is_active",
            "email_verified",
            "password",
        ])

        # Delete old profile in case the user changed role during re-registration.
        Student.objects.filter(user=user).delete()
        Company.objects.filter(user=user).delete()
        AdminProfile.objects.filter(user=user).delete()

        return user

    def create_role_profile(self, user, role, name, validated_data):
        """
        Create the correct profile table based on the selected role.
        """
        if role == "STUDENT":
            Student.objects.create(
                user=user,
                student_name=name,
                department=validated_data.get("department", ""),
                desired_job_category=validated_data.get(
                    "desired_job_category",
                    "",
                ),
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


# ============================================================
# Password reset request serializer
# ============================================================

class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Handles forgot password request.

    It sends a password reset link if the email exists.
    It does not reveal whether the email exists for security reasons.
    """

    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.lower().strip()

        validate_real_email_domain(email)

        return email

    def save(self):
        email = self.validated_data["email"]
        user = User.objects.filter(email=email).first()

        if user:
            send_password_reset_email(user)


# ============================================================
# Password reset confirm serializer
# ============================================================

class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Handles setting a new password from the reset password link.
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        password = data["password"]

        if password != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": ["Passwords do not match."]
            })

        validate_strong_password(password)

        user = get_user_from_uid(data["uid"])

        if not user:
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


# ============================================================
# Custom login serializer
# ============================================================

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Customizes login error message.

    If a user exists but has not verified email,
    return a clear message instead of the default JWT error.
    """

    def validate(self, attrs):
        email = attrs.get(self.username_field, "").lower().strip()
        user = User.objects.filter(email=email).first()

        if user and (not user.is_active or not user.email_verified):
            raise AuthenticationFailed(
                "Please verify your email before logging in. Check your inbox for the verification link."
            )

        return super().validate(attrs)