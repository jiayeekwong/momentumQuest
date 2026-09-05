import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .audit import record_privacy_event
from .departments import DEPARTMENTS, validate_department
from .models import (
    AdminProfile,
    Company,
    PrivacyAuditLog,
    Student,
    StudentSkill,
    StudentTargetRole,
    UserConsent,
)
from .privacy_notice import CURRENT_VERSION


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


@transaction.atomic
def set_student_target_roles(student, role_names):
    """Replace a student's target careers with the given Market Role names.

    The single writer for a student's career target.

    Validation happens before anything is deleted. Writing first meant a typo
    or a stale client value wiped a valid career target and returned 200 --
    the student lost their target and was told it succeeded.

    Unknown names raise instead of being skipped, for the same reason: a
    request naming three roles of which one is wrong should fail loudly, not
    silently store two.
    """
    from scrape_jobs.models import MarketRole

    # Accepts "Data Analyst" or {"market_role": "Data Analyst"}; the object
    # form is what the picker sends.
    requested = []
    for entry in (role_names or []):
        if isinstance(entry, dict):
            name = str(entry.get("market_role")
                       or entry.get("role_name") or "").strip()
        else:
            name = str(entry).strip()
        if name:
            requested.append(name)

    roles = []
    if requested:
        known = {
            role.name: role
            for role in MarketRole.objects.filter(name__in=requested,
                                                  is_active=True)
        }
        unknown = [name for name in requested if name not in known]
        if unknown:
            raise serializers.ValidationError({
                "target_roles": [f"Unknown Market Role: {name}" for name in unknown]
            })
        # De-duplicated while preserving the order the student sent.
        seen = set()
        roles = [known[n] for n in requested if not (n in seen or seen.add(n))]

    StudentTargetRole.objects.filter(student=student).delete()
    StudentTargetRole.objects.bulk_create([
        StudentTargetRole(student=student, market_role=role) for role in roles
    ])





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
    # Self-service registration creates students and companies only.
    #
    # Never User.Role.choices: that list includes ADMIN, so anyone could POST
    # role="ADMIN", verify their own email, and receive an AdminProfile plus
    # every permission gated on role == "ADMIN" -- certificate review,
    # identity documents, the admin dashboard. Administrators are created out
    # of band by `manage.py create_admin` or `createsuperuser`, both of which
    # also set is_staff, which IsAdminUserRole now requires.
    role = serializers.ChoiceField(choices=[
        (User.Role.STUDENT, User.Role.STUDENT.label),
        (User.Role.COMPANY, User.Role.COMPANY.label),
    ])

    name = serializers.CharField(max_length=100, write_only=True)

    department = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
    )

    # University enrolment number. Not an identity-document number -- see the
    # comment on Student.matric_number.
    matric_number = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        write_only=True,
    )

    # The privacy acknowledgement is mandatory for everyone. It must arrive as
    # an explicit true: declaring it required (rather than default=False) means
    # an older client that omits it fails loudly instead of silently creating
    # an unconsented account.
    privacy_notice_accepted = serializers.BooleanField(write_only=True)
    # Document verification is a student function. A company or admin account
    # never submits a certificate for verification, so asking them to consent
    # to it would be asking for permission that is never exercised -- and a
    # stored consent nothing acts on is noise in the record, not evidence.
    document_verification_consent = serializers.BooleanField(
        write_only=True, required=False, default=False)

    # Market Role names the student is targeting. Names rather than IDs so a
    # client can post the career it displayed without a second round trip;
    # Market Role names are unique, so a name identifies exactly one career.
    target_roles = serializers.ListField(
        child=serializers.CharField(max_length=200),
        required=False,
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

        # The department list is served from the backend, so a value outside it
        # means a stale client or a hand-made request, not a new department.
        if data.get("role") == User.Role.STUDENT:
            validate_department(data.get("department", ""))

        # An account must not exist without consent, so this is a hard gate
        # rather than a frontend courtesy -- the sign-up page disables its
        # button, but nothing stops a direct POST.
        if not data.get("privacy_notice_accepted"):
            raise serializers.ValidationError({
                "privacy_notice_accepted": [
                    "You must read and acknowledge the Privacy Notice to create an account."
                ]
            })

        if (data.get("role") == User.Role.STUDENT
                and not data.get("document_verification_consent")):
            raise serializers.ValidationError({
                "document_verification_consent": [
                    "You must consent to the processing of documents you submit for "
                    "qualification and skill verification to create a student account."
                ]
            })

        existing_user = User.objects.filter(email=email).first()

        if existing_user:
            if existing_user.email_verified and existing_user.is_active:
                raise serializers.ValidationError({
                    "email": ["Email is already registered. Please login instead."]
                })

            # An administrator account is never re-registerable, verified or
            # not. The unverified-reuse path exists so someone who lost their
            # verification email can start again; letting it apply to an admin
            # would turn "register with a known admin address" into a way to
            # take the account over and demote it into a student profile.
            if (existing_user.role == User.Role.ADMIN
                    or existing_user.is_staff
                    or existing_user.is_superuser):
                raise serializers.ValidationError({
                    "email": ["Email is already registered. Please login instead."]
                })

            self.existing_unverified_user = existing_user

        return data

    def create(self, validated_data):
        role = validated_data["role"]
        name = validated_data["name"]

        # The account, its profile and its consent records are written as one
        # unit. Recording consent through a separate request afterwards would
        # leave a window in which an account exists with no consent on file.
        with transaction.atomic():
            existing_user = getattr(self, "existing_unverified_user", None)

            if existing_user:
                user = self.update_existing_unverified_user(
                    existing_user,
                    validated_data,
                )

            else:
                user = self.create_new_inactive_user(validated_data)

            self.create_role_profile(user, role, name, validated_data)

            consents = self.record_signup_consents(user)

        # Outside the transaction: neither an audit write nor an SMTP call
        # should be able to roll back a completed registration.
        for consent in consents:
            record_privacy_event(
                PrivacyAuditLog.Action.CONSENT_ACCEPTED,
                actor=user,
                target=user,
                resource_id=consent.pk,
                resource_type=PrivacyAuditLog.ResourceType.CONSENT,
                request=self.context.get("request"),
            )

        send_verification_email(user, name)

        return user

    def record_signup_consents(self, user):
        """Write one row per consent type against the current notice version.

        Which types depends on the role: everyone acknowledges the notice, but
        only a student is asked to consent to document verification, because
        only a student ever submits a document to be verified.

        A re-registering unverified user passes through here again and gains a
        second set of rows. That is intended: they were shown the notice and
        agreed a second time, and the table is a history of acts of consent,
        not a set of current flags.
        """
        accepted_at = timezone.now()

        consent_types = [UserConsent.ConsentType.PRIVACY_NOTICE_ACKNOWLEDGEMENT]
        if user.role == User.Role.STUDENT:
            consent_types.append(
                UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT)

        return [
            UserConsent.objects.create(
                user=user,
                consent_type=consent_type,
                notice_version=CURRENT_VERSION,
                accepted=True,
                accepted_at=accepted_at,
                source=UserConsent.Source.SIGNUP,
            )
            for consent_type in consent_types
        ]

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

        Only the two self-service roles are handled. There is deliberately no
        ADMIN branch: the field rejects that value already, and a second,
        silent path to an AdminProfile is exactly the shape of the bug this
        replaced.
        """
        if role == "STUDENT":
            student = Student.objects.create(
                user=user,
                student_name=name,
                department=validated_data.get("department", ""),
                matric_number=validated_data.get("matric_number", "").strip(),
            )
            # The Market Role is the only career target a user chooses;
            # everything else derives from it.
            set_student_target_roles(student, validated_data.get("target_roles", []))

        elif role == "COMPANY":
            Company.objects.create(
                user=user,
                company_name=name,
            )

        else:
            raise serializers.ValidationError({
                "role": ["Accounts of this type cannot be self-registered."]
            })


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


# ============================================================
# Student skill serializer
# ============================================================

class StudentSkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source='skill.skill_name', read_only=True)

    class Meta:
        model = StudentSkill
        fields = ['skill_name', 'skill_level']


class UserConsentSerializer(serializers.ModelSerializer):
    """Read-only view of a user's own consent history.

    ``statement`` is resolved from the notice module so the user is shown the
    wording they actually agreed to rather than a bare enum value.
    """
    statement = serializers.SerializerMethodField()

    class Meta:
        model = UserConsent
        fields = [
            'id', 'consent_type', 'statement', 'notice_version', 'accepted',
            'accepted_at', 'withdrawn_at', 'source', 'created_at',
        ]

    def get_statement(self, obj):
        from .privacy_notice import CONSENT_STATEMENTS
        return CONSENT_STATEMENTS.get(obj.consent_type, '')
