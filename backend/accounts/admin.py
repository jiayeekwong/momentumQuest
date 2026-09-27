from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group

from .forms import UserChangeForm, UserCreationForm
from .models import (
    AdminProfile,
    Company,
    PrivacyAuditLog,
    SkillGap,
    Student,
    RoleTerminologyFeedback,
    StudentTargetRole,
    User,
    UserConsent,
)

#: A user is only half an account. The row in `accounts_user` carries the
#: login and the role; what the rest of the application reads -- a student's
#: name and department, a company's details, the administrator a record is
#: attributed to -- lives in a separate table joined one-to-one.
#:
#: Nothing created those alongside the user. Sign-up creates a Student or a
#: Company through the registration serializer, and `manage.py create_admin`
#: creates an AdminProfile; the admin's Add User form went through neither, so
#: every account made here was missing the half the application actually uses.
#: The first symptom was a 500 on publishing an announcement.
#:
#: Shown as inlines rather than created silently. An administrator filling one
#: in is making a decision the application can attribute; a profile conjured
#: by a signal is a second, silent path to an AdminProfile, which is the shape
#: of a bug this codebase has already replaced once.


class StudentInline(admin.StackedInline):
    model = Student
    can_delete = False
    extra = 1
    max_num = 1
    verbose_name = "Student profile"
    verbose_name_plural = "Student profile"


class CompanyInline(admin.StackedInline):
    model = Company
    can_delete = False
    extra = 1
    max_num = 1
    verbose_name = "Company profile"
    verbose_name_plural = "Company profile"


class AdminProfileInline(admin.StackedInline):
    model = AdminProfile
    can_delete = False
    extra = 1
    max_num = 1
    verbose_name = "Administrator profile"
    verbose_name_plural = "Administrator profile"


PROFILE_INLINES = {
    User.Role.STUDENT: StudentInline,
    User.Role.COMPANY: CompanyInline,
    User.Role.ADMIN: AdminProfileInline,
}


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """The user admin, with Django's password handling rather than a text box.

    Registered with `admin.site.register(User)` before this, which gave it the
    default ModelAdmin: a plain ModelForm over every editable field, including
    `password`. AbstractBaseUser declares that as an ordinary CharField, so the
    Add User page showed one visible password box and stored whatever was typed,
    unhashed. Those accounts could not log in, and their passwords sat in the
    database in clear text.

    Django's UserAdmin is the fix, but not unmodified: its add_fieldsets name a
    `username` field this model does not have, so both fieldsets are declared
    here against `email`.

    `groups` and `user_permissions` are deliberately absent. This project
    authorises on the custom `role` field -- which is why Group is unregistered
    at the bottom of this module -- and offering permission widgets that nothing
    reads would invite an administrator to grant access that has no effect.
    """

    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    ordering = ("email",)
    list_display = ("email", "role", "is_active", "email_verified", "is_staff",
                    "created_time")
    list_filter = ("role", "is_active", "is_staff", "is_superuser",
                   "email_verified")
    search_fields = ("email",)
    readonly_fields = ("last_login",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Role and access", {
            "fields": ("role", "email_verified", "is_active", "is_staff",
                       "is_superuser"),
        }),
        ("Dates", {"fields": ("last_login", "created_time")}),
    )

    # usable_password is Django's own control for creating an account that
    # cannot be signed into with a password; it comes from AdminUserCreationForm
    # and has to be listed or the admin will not render it.
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "role", "usable_password", "password1",
                       "password2"),
        }),
    )

    def get_inline_instances(self, request, obj=None):
        """The profile for this user's role, and only once there is a role.

        None on the Add page: the role is chosen in the same submission, so
        there is nothing yet to decide which profile applies. Django sends the
        administrator to the change page immediately after adding, which is
        where the inline appears -- and the system check in accounts/checks.py
        is what catches an account where somebody stopped at the first page.
        """
        if obj is None:
            return []
        inline = PROFILE_INLINES.get(obj.role)
        if inline is None:
            return []
        return [inline(self.model, self.admin_site)]
admin.site.register(Student)
admin.site.register(Company)
admin.site.register(AdminProfile)
admin.site.register(StudentTargetRole)
admin.site.register(RoleTerminologyFeedback)
admin.site.register(SkillGap)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Browsable but immutable.

    Consent records and audit entries are evidence. If they can be edited from
    the admin site they prove nothing, so the only supported operation is
    reading them.
    """

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserConsent)
class UserConsentAdmin(ReadOnlyAdmin):
    list_display  = ("user", "consent_type", "notice_version", "accepted",
                     "accepted_at", "source")
    list_filter   = ("consent_type", "accepted", "notice_version", "source")
    search_fields = ("user__email",)
    date_hierarchy = "created_at"


@admin.register(PrivacyAuditLog)
class PrivacyAuditLogAdmin(ReadOnlyAdmin):
    list_display  = ("timestamp", "actor_user", "action", "target_user",
                     "resource_type", "resource_id")
    list_filter   = ("action", "resource_type")
    search_fields = ("actor_user__email", "target_user__email")
    date_hierarchy = "timestamp"

# Hide Django's built-in Groups from the admin — this project uses the custom
# `role` field for authorization, not Django Groups.
admin.site.unregister(Group)
