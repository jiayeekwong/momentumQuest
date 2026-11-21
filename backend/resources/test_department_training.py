from rest_framework.test import APITestCase

from accounts.models import AdminProfile, Company, Department, Student, User
from resources.models import TrainingProgramme


class DepartmentTrainingWorkflowTests(APITestCase):
    def setUp(self):
        self.software, _ = Department.objects.get_or_create(
            code="SE", defaults={"name": "Software Engineering"})
        self.ai, _ = Department.objects.get_or_create(
            code="AI", defaults={"name": "Artificial Intelligence"})
        company_user = User.objects.create_user(
            email="training-company@university.edu", password="Strong-Pass-1!",
            role=User.Role.COMPANY, email_verified=True)
        self.company = Company.objects.create(
            user=company_user, company_name="Training Company")
        self.company_user = company_user
        self.software_admin = self._admin(
            "software-reviewer@university.edu", self.software)
        self.ai_admin = self._admin("ai-reviewer@university.edu", self.ai)
        self.software_student = self._student(
            "software-reader@university.edu", self.software)
        self.ai_student = self._student(
            "ai-reader@university.edu", self.ai)

    @staticmethod
    def _admin(email, department):
        user = User.objects.create_user(
            email=email, password="Strong-Pass-1!", role=User.Role.ADMIN,
            is_staff=True, email_verified=True)
        AdminProfile.objects.create(
            user=user, admin_name=email.split("@")[0], department=department)
        return user

    @staticmethod
    def _student(email, department):
        user = User.objects.create_user(
            email=email, password="Strong-Pass-1!", role=User.Role.STUDENT,
            email_verified=True)
        Student.objects.create(
            user=user, student_name=email.split("@")[0], department=department)
        return user

    def _programme(self, department=None):
        return TrainingProgramme.objects.create(
            company=self.company, department=department or self.software,
            title="Secure Software Training")

    def test_company_must_choose_the_reviewing_department(self):
        self.client.force_authenticate(self.company_user)
        missing = self.client.post("/api/resources/training/", {
            "title": "No department",
        }, format="json")
        created = self.client.post("/api/resources/training/", {
            "title": "AI Training", "department": self.ai.name,
        }, format="json")

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["department"], self.ai.name)

    def test_only_the_selected_department_admin_can_review(self):
        programme = self._programme()
        url = f"/api/resources/training/admin/{programme.pk}/review/"
        self.client.force_authenticate(self.ai_admin)
        refused = self.client.patch(url, {
            "approval_status": "APPROVED", "visibility": "DEPARTMENT",
        }, format="json")
        self.client.force_authenticate(self.software_admin)
        accepted = self.client.patch(url, {
            "approval_status": "APPROVED", "visibility": "DEPARTMENT",
        }, format="json")

        self.assertEqual(refused.status_code, 404)
        self.assertEqual(accepted.status_code, 200, accepted.data)

    def test_department_visibility_only_lists_for_matching_students(self):
        programme = self._programme()
        programme.approval_status = TrainingProgramme.ApprovalStatus.APPROVED
        programme.visibility = TrainingProgramme.Visibility.DEPARTMENT
        programme.save()

        self.client.force_authenticate(self.software_student)
        software_rows = self.client.get("/api/resources/training/approved/").data
        self.client.force_authenticate(self.ai_student)
        ai_rows = self.client.get("/api/resources/training/approved/").data

        software_rows = (software_rows.get("results", [])
                         if isinstance(software_rows, dict) else software_rows)
        ai_rows = (ai_rows.get("results", [])
                   if isinstance(ai_rows, dict) else ai_rows)
        self.assertIn(programme.pk, [row["id"] for row in software_rows])
        self.assertNotIn(programme.pk, [row["id"] for row in ai_rows])

    def test_everyone_visibility_lists_for_all_students(self):
        programme = self._programme()
        programme.approval_status = TrainingProgramme.ApprovalStatus.APPROVED
        programme.visibility = TrainingProgramme.Visibility.EVERYONE
        programme.save()

        for user in (self.software_student, self.ai_student):
            self.client.force_authenticate(user)
            data = self.client.get("/api/resources/training/approved/").data
            rows = data.get("results", []) if isinstance(data, dict) else data
            self.assertIn(programme.pk, [row["id"] for row in rows])
