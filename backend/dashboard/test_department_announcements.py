from rest_framework.test import APITestCase

from accounts.models import AdminProfile, Company, Department, Student, User


class DepartmentAnnouncementAudienceTests(APITestCase):
    def setUp(self):
        self.software, _ = Department.objects.get_or_create(
            code="SE", defaults={"name": "Software Engineering"})
        self.ai, _ = Department.objects.get_or_create(
            code="AI", defaults={"name": "Artificial Intelligence"})
        self.admin = User.objects.create_user(
            email="se-admin@university.edu", password="Strong-Pass-1!",
            role=User.Role.ADMIN, is_staff=True, email_verified=True)
        AdminProfile.objects.create(
            user=self.admin, admin_name="SE Admin", department=self.software)
        self.superadmin = User.objects.create_user(
            email="super@university.edu", password="Strong-Pass-1!",
            role=User.Role.ADMIN, is_staff=True, is_superuser=True,
            email_verified=True)
        AdminProfile.objects.create(user=self.superadmin, admin_name="Super")
        self.software_student = self._student(
            "software-student@university.edu", self.software)
        self.ai_student = self._student(
            "ai-student@university.edu", self.ai)
        self.company = User.objects.create_user(
            email="company-announcement@university.edu", password="Strong-Pass-1!",
            role=User.Role.COMPANY, email_verified=True)
        Company.objects.create(user=self.company, company_name="Company")

    @staticmethod
    def _student(email, department):
        user = User.objects.create_user(
            email=email, password="Strong-Pass-1!", role=User.Role.STUDENT,
            email_verified=True)
        Student.objects.create(
            user=user, student_name=email.split("@")[0], department=department)
        return user

    def _publish(self, user, audience, targets=None):
        self.client.force_authenticate(user)
        return self.client.post("/api/dashboard/announcements/create/", {
            "title": "Department update",
            "message": "<p>Important update.</p>",
            "audience": audience,
            "target_departments": targets or [],
        }, format="json")

    def _visible_titles(self, user):
        self.client.force_authenticate(user)
        response = self.client.get("/api/dashboard/announcements/")
        self.assertEqual(response.status_code, 200)
        return [item["title"] for item in response.data]

    def test_department_admin_can_only_target_their_own_department(self):
        refused = self._publish(self.admin, "STUDENTS", [self.ai.name])
        allowed = self._publish(self.admin, "STUDENTS", [self.software.name])

        self.assertEqual(refused.status_code, 400)
        self.assertEqual(allowed.status_code, 201, allowed.data)
        self.assertIn("Department update", self._visible_titles(self.software_student))
        self.assertNotIn("Department update", self._visible_titles(self.ai_student))
        self.assertNotIn("Department update", self._visible_titles(self.company))

    def test_superadmin_can_target_another_department(self):
        response = self._publish(self.superadmin, "STUDENTS", [self.ai.name])

        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("Department update", self._visible_titles(self.software_student))
        self.assertIn("Department update", self._visible_titles(self.ai_student))

    def test_everyone_reaches_students_and_companies(self):
        response = self._publish(self.admin, "EVERYONE")

        self.assertEqual(response.status_code, 201, response.data)
        for user in (self.software_student, self.ai_student, self.company):
            self.assertIn("Department update", self._visible_titles(user))

    def test_department_admin_can_target_companies_only(self):
        response = self._publish(
            self.admin, "COMPANIES", [self.software.name])

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["audience"], "COMPANIES")
        self.assertEqual(response.data["target_departments"], [])
        self.assertNotIn(
            "Department update", self._visible_titles(self.software_student))
        self.assertNotIn(
            "Department update", self._visible_titles(self.ai_student))
        self.assertIn("Department update", self._visible_titles(self.company))
