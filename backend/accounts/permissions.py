from rest_framework import permissions


def is_platform_admin(user):
    """Whether ``user`` is an administrator of this platform.

    The single definition, used by permission classes and by the view code
    that picks an admin serializer or an unscoped queryset. Those decisions
    are access control too -- CertificateAdminSerializer exposes internal
    verification notes, and the admin queryset is every student's documents --
    so they must not test the role on their own.
    """
    return bool(
        getattr(user, "is_authenticated", False)
        and user.role == "ADMIN"
        and user.is_staff
    )


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
    reach certificate review, student identity documents or the admin
    dashboard.
    """

    def has_permission(self, request, view):
        return is_platform_admin(request.user)