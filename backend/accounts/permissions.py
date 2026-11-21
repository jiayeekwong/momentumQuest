from rest_framework import permissions
from rest_framework.exceptions import APIException


def is_platform_admin(user):
    """Whether ``user`` is an administrator of this platform.

    The single definition used by permission classes and view code for
    platform-administration functions. Requiring both role and staff status
    keeps ordinary application data from granting administrative access.
    """
    return bool(
        getattr(user, "is_authenticated", False)
        and user.role == "ADMIN"
        and user.is_staff
    )


def is_superadmin(user):
    """Global administration is deliberately narrower than platform admin."""
    return bool(is_platform_admin(user) and user.is_superuser)


class IsStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'STUDENT'


class IsCompany(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'COMPANY'


class IsAdminUserRole(permissions.BasePermission):
    """Administrative access: the ADMIN role *and* the staff flag.

    Two independent facts, deliberately. ``role`` is application data that a
    registration payload used to be able to set; ``is_staff`` is only ever
    granted out of band, by `manage.py create_admin` or `createsuperuser`.
    Requiring both means a single writable field can never again be enough to
    reach administrative dashboards or management functions.
    """

    def has_permission(self, request, view):
        return is_platform_admin(request.user)


class IsSuperAdmin(permissions.BasePermission):
    """Operations that can grant authority require a Django superuser."""

    def has_permission(self, request, view):
        return is_superadmin(request.user)

class AdminProfileMissing(APIException):
    """An administrator account that was never finished being set up.

    Administrators are made out of band, and only `manage.py create_admin`
    creates the AdminProfile alongside the user. `createsuperuser` does not,
    and neither does adding a user through the Django admin -- so an account
    can pass every permission check here, hold every admin power, and still
    have no profile row to attribute its work to.

    Five endpoints attributed a record to `request.user.admin_profile`
    directly. On such an account that raises inside the view, which reaches
    the client as a 500 and an HTML error page -- the form showed the operator
    an empty object and no way to tell what was wrong.

    Deliberately not fixed by creating the profile here. A second, silent path
    to an AdminProfile is the shape of a bug this codebase has already
    replaced once, and the accounts serializer says so. The account is
    incomplete; this says so, and says how to complete it.
    """

    status_code = 409
    default_detail = (
        "This administrator account has no admin profile, so the record "
        "cannot be attributed to anyone. Run: manage.py create_admin "
        "--email <this account> --name \"<display name>\""
    )
    default_code = "admin_profile_missing"


def admin_profile_for(user):
    """The AdminProfile that owns what this administrator creates.

    Raises AdminProfileMissing rather than letting the attribute error surface
    as a server error. getattr with a default is safe here: Django's
    RelatedObjectDoesNotExist subclasses AttributeError for exactly this.
    """
    profile = getattr(user, "admin_profile", None)
    if profile is None:
        raise AdminProfileMissing()
    return profile
