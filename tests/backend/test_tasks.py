"""
Tests for the tasks API endpoints (backing the header Tasks modal).
"""
import pytest

import main  # server/ is put on sys.path by conftest.py


@pytest.fixture(autouse=True)
def clear_tasks():
    """Tasks live in module-level memory, so reset them around every test."""
    main.tasks.clear()
    yield
    main.tasks.clear()


def _create(client, title="Check Q4 stock", priority="high", due="2025-10-08"):
    return client.post("/api/tasks", json={"title": title, "priority": priority, "dueDate": due})


class TestTasksEndpoints:
    """Test suite for task endpoints."""

    def test_get_tasks_empty(self, client):
        """Test that the task list starts empty."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client):
        """Test creating a task returns it as pending with a string ID."""
        response = _create(client)
        assert response.status_code == 201

        task = response.json()
        assert isinstance(task["id"], str)
        assert task["title"] == "Check Q4 stock"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-08"
        assert task["status"] == "pending"

    def test_get_tasks_newest_first(self, client):
        """Test that created tasks are listed newest first."""
        first = _create(client, title="First").json()
        second = _create(client, title="Second").json()

        data = client.get("/api/tasks").json()
        assert [t["id"] for t in data] == [second["id"], first["id"]]

    def test_create_task_ids_not_reused_after_delete(self, client):
        """Test that deleting a task doesn't cause the next one to reuse its ID."""
        first = _create(client).json()
        client.delete(f"/api/tasks/{first['id']}")
        second = _create(client).json()
        assert second["id"] != first["id"]

    def test_create_task_blank_title(self, client):
        """Test that a whitespace-only title is rejected."""
        response = _create(client, title="   ")
        assert response.status_code == 400

    def test_create_task_invalid_priority(self, client):
        """Test that an unknown priority is rejected."""
        response = _create(client, priority="urgent")
        assert response.status_code == 400

    def test_create_task_missing_due_date(self, client):
        """Test that dueDate is required."""
        response = client.post("/api/tasks", json={"title": "No date"})
        assert response.status_code == 422

    def test_toggle_task(self, client):
        """Test that PATCH flips status pending -> completed -> pending."""
        task_id = _create(client).json()["id"]

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "pending"

    def test_toggle_nonexistent_task(self, client):
        """Test toggling a task that doesn't exist."""
        response = client.patch("/api/tasks/nonexistent-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_task(self, client):
        """Test deleting a task removes it from the list."""
        task_id = _create(client).json()["id"]

        response = client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert client.get("/api/tasks").json() == []

    def test_delete_nonexistent_task(self, client):
        """Test deleting a task that doesn't exist."""
        response = client.delete("/api/tasks/nonexistent-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
