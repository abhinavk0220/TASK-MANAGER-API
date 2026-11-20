from django.test import TestCase
from rest_framework.test import APIClient

from .ai import break_down_task
from .models import Task
from .views import IDEMPOTENCY_STORE


class TaskApiTests(TestCase):
    def setUp(self):
        IDEMPOTENCY_STORE.clear()
        self.client = APIClient()

    def test_validation_error_shape(self):
        response = self.client.post(
            "/api/tasks/",
            {"title": "", "description": "", "completed": "yes", "priority": "urgent"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertIsInstance(response.json()["error"]["message"], str)

    def test_impossible_due_date(self):
        response = self.client.post(
            "/api/tasks/",
            {
                "title": "Test",
                "description": "Impossible date",
                "due_date": "2026-02-30",
                "completed": False,
                "priority": "low",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_text_creation_and_parser(self):
        response = self.client.post(
            "/api/tasks/from-text/",
            {"text": "Remind me to pay rent on the 1st of every month"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("rent", response.json()["title"].lower())
        self.assertEqual(response.json()["recurrence"], "monthly")

    def test_subtask_creation_and_cascade_delete(self):
        parent = Task.objects.create(
            title="Parent", description="Parent task", completed=False
        )
        response = self.client.post(
            f"/api/tasks/{parent.pk}/subtasks/",
            {"title": "Child", "description": "Child task", "completed": False},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        child_id = response.json()["id"]

        parent.delete()
        self.assertFalse(Task.objects.filter(pk=child_id).exists())

    def test_subtask_cannot_have_subtask(self):
        parent = Task.objects.create(title="Parent", description="Parent")
        child = Task.objects.create(
            title="Child", description="Child", parent=parent
        )
        response = self.client.post(
            f"/api/tasks/{child.pk}/subtasks/",
            {"title": "Grandchild", "description": "Invalid"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_breakdown_and_subtask_rule(self):
        task = Task.objects.create(
            title="buy milk and call Alex",
            description="Prepare errands",
            priority="high",
        )
        response = self.client.post(
            f"/api/tasks/{task.pk}/breakdown/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertGreaterEqual(len(response.json()), 2)
        self.assertFalse(Task.objects.filter(pk=task.pk, parent__isnull=False).exists())

    def test_idempotency_same_key_same_body(self):
        payload = {
            "title": "Retry once",
            "description": "Should create once",
            "completed": False,
            "priority": "medium",
        }
        headers = {"HTTP_IDEMPOTENCY_KEY": "repeat-key"}
        first = self.client.post("/api/tasks/", payload, format="json", **headers)
        second = self.client.post("/api/tasks/", payload, format="json", **headers)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(Task.objects.filter(title="Retry once").count(), 1)
        self.assertEqual(first.json(), second.json())

    def test_idempotency_key_conflict(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "conflict-key"}
        first = self.client.post(
            "/api/tasks/",
            {"title": "First", "description": "Body one", "completed": False},
            format="json",
            **headers,
        )
        second = self.client.post(
            "/api/tasks/",
            {"title": "Second", "description": "Body two", "completed": False},
            format="json",
            **headers,
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 422)
        self.assertEqual(second.json()["error"]["code"], "IDEMPOTENCY_KEY_CONFLICT")

    def test_filter_search_order_and_pagination(self):
        for index in range(15):
            Task.objects.create(
                title=f"alpha task {index}",
                description="shared description",
                completed=index % 2 == 0,
                priority="high" if index % 2 == 0 else "low",
            )
        response = self.client.get(
            "/api/tasks/?completed=true&priority=high&search=alpha&ordering=title&page=1"
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("results", body)
        self.assertIn("count", body)
        self.assertLessEqual(len(body["results"]), 10)

    def test_unknown_task_uses_error_shape(self):
        response = self.client.get("/api/tasks/999999/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    def test_bad_parser_output_returns_502_without_save(self):
        from unittest.mock import patch

        with patch("tasks.views.parse_task_text", return_value={
            "title": "",
            "description": "Bad parser output",
            "due_date": None,
            "recurrence": None,
        }):
            response = self.client.post(
                "/api/tasks/from-text/",
                {"text": "Remind me to do nothing"},
                format="json",
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "PARSER_OUTPUT_INVALID")
        self.assertEqual(Task.objects.count(), 0)
