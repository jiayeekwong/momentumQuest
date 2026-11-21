import re

from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import AdminInvitation, AdminProfile, Department, User


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="MomentumQuest <system@example.edu>",
    FRONTEND_URL="https://momentumquest.example.edu",
)
class AdminInvitationFlowTests(APITestCase):
    def setUp(self):
        self.department, _ = Department.objects.get_or_create(
            code="SE", defaults={"name": "Software Engineering"})
        self.superadmin = User.objects.create_user(
            email="superadmin@university.edu", password="Strong-Pass-1!",
            role=User.Role.ADMIN, is_staff=True, is_superuser=True,
            email_verified=True)
        AdminProfile.objects.create(
            user=self.superadmin, admin_name="Super Admin")
        self.department_admin = User.objects.create_user(
            email="department-admin@university.edu", password="Strong-Pass-1!",
            role=User.Role.ADMIN, is_staff=True, email_verified=True)
        AdminProfile.objects.create(
            user=self.department_admin, admin_name="Department Admin",
            department=self.department)

    def _invite(self, email="new-admin@university.edu"):
        self.client.force_authenticate(self.superadmin)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post("/api/auth/admin-invitations/", {
                "email": email,
                "department": self.department.name,
            }, format="json")

    def test_only_a_superadmin_can_send_an_invitation(self):
        self.client.force_authenticate(self.department_admin)

        response = self.client.post("/api/auth/admin-invitations/", {
            "email": "blocked@university.edu",
            "department": self.department.name,
        }, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AdminInvitation.objects.filter(
            email="blocked@university.edu").exists())

    def test_invitation_email_contains_the_single_use_signup_link(self):
        response = self._invite()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accept-admin-invitation?token=", mail.outbox[0].body)
        invitation = AdminInvitation.objects.get(email="new-admin@university.edu")
        self.assertEqual(invitation.department, self.department)
        self.assertEqual(invitation.status, AdminInvitation.Status.PENDING)

    def test_invited_person_creates_a_department_admin_account(self):
        self.assertEqual(self._invite().status_code, 201)
        token = re.search(
            r"/accept-admin-invitation\?token=([^\s]+)",
            mail.outbox[0].body,
        ).group(1)
        self.client.force_authenticate(user=None)

        response = self.client.post("/api/auth/admin-invitations/accept/", {
            "token": token,
            "name": "New Department Admin",
            "password": "Strong-Pass-2!",
            "confirm_password": "Strong-Pass-2!",
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="new-admin@university.edu")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.admin_profile.department, self.department)
        invitation = AdminInvitation.objects.get(email=user.email)
        self.assertEqual(invitation.status, AdminInvitation.Status.ACCEPTED)

        replay = self.client.post("/api/auth/admin-invitations/accept/", {
            "token": token,
            "name": "Replay",
            "password": "Strong-Pass-3!",
            "confirm_password": "Strong-Pass-3!",
        }, format="json")
        self.assertEqual(replay.status_code, 400)


class StudentDepartmentProfileTests(APITestCase):
    def test_a_student_can_correct_their_department(self):
        from .models import PrivacyAuditLog, Student

        first, _ = Department.objects.get_or_create(
            code="SE", defaults={"name": "Software Engineering"})
        second, _ = Department.objects.get_or_create(
            code="AI", defaults={"name": "Artificial Intelligence"})
        user = User.objects.create_user(
            email="student-change@university.edu", password="Strong-Pass-1!",
            role=User.Role.STUDENT, email_verified=True)
        Student.objects.create(
            user=user, student_name="Student", department=first)
        self.client.force_authenticate(user)

        response = self.client.patch("/api/auth/profile/", {
            "department": second.name,
        }, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["department"], second.name)
        self.assertTrue(PrivacyAuditLog.objects.filter(
            target_user=user,
            action=PrivacyAuditLog.Action.DEPARTMENT_CHANGED,
        ).exists())
