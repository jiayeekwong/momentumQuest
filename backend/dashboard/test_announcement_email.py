from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import AdminProfile, Student, User


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="MomentumQuest <system@example.edu>",
    FRONTEND_URL="https://momentumquest.example.edu",
)
class AnnouncementEmailNotificationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.edu", password="Sufficient-Pass-1",
            role=User.Role.ADMIN, is_staff=True, is_active=True,
            email_verified=True,
        )
        AdminProfile.objects.create(user=self.admin, admin_name="Admin")
        self.client.force_authenticate(self.admin)

        self.student = self._student("student@example.edu")
        self._student("unverified@example.edu", email_verified=False)
        self._student("inactive@example.edu", is_active=False)
        self.company = User.objects.create_user(
            email="company@example.edu", password="Sufficient-Pass-1",
            role=User.Role.COMPANY, is_active=True, email_verified=True,
        )

    @staticmethod
    def _student(email, *, email_verified=True, is_active=True):
        user = User.objects.create_user(
            email=email, password="Sufficient-Pass-1", role=User.Role.STUDENT,
            email_verified=email_verified, is_active=is_active,
        )
        Student.objects.create(user=user, student_name=email.split("@")[0])
        return user

    def _publish(self, audience):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/dashboard/announcements/create/", {
                "title": "Career Fair",
                "message": "<p>Meet employers <strong>tomorrow</strong>.</p>",
                "audience": audience,
            }, format="json")
        self.assertEqual(response.status_code, 201)

    def test_students_audience_emails_active_verified_students_individually(self):
        self._publish("STUDENTS")

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.student.email])
        self.assertIn("Career Fair", message.subject)
        self.assertIn("Meet employers tomorrow.", message.body)
        self.assertIn("https://momentumquest.example.edu/dashboard", message.body)

    def test_everyone_audience_emails_active_verified_students_and_companies(self):
        self._publish("EVERYONE")

        self.assertCountEqual(
            [message.to for message in mail.outbox],
            [[self.student.email], [self.company.email]],
        )

    def test_companies_audience_emails_companies_but_not_students(self):
        self._publish("COMPANIES")

        self.assertEqual([message.to for message in mail.outbox], [[self.company.email]])
