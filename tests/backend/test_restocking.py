"""
Tests for restocking API endpoints.
"""
from datetime import date, datetime, timedelta

import pytest

import main  # server/ is put on sys.path by conftest.py


@pytest.fixture(autouse=True)
def clear_restock_orders():
    """Restock orders live in module-level memory; reset them around every test."""
    main.restock_orders.clear()
    yield
    main.restock_orders.clear()


def recommendations_by_sku(client):
    response = client.get("/api/restock/recommendations")
    assert response.status_code == 200
    return {row["sku"]: row for row in response.json()}


class TestRestockRecommendations:
    """Test suite for GET /api/restock/recommendations."""

    def test_get_all_recommendations(self, client):
        """Test that every demand forecast gets one recommendation row."""
        response = client.get("/api/restock/recommendations")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == len(client.get("/api/demand").json())

        expected_fields = [
            "sku", "name", "category", "trend", "current_demand", "forecasted_demand",
            "stock_on_hand", "suggested_quantity", "unit_cost", "line_cost",
            "lead_time_days", "already_ordered", "urgency_rank",
        ]
        for row in data:
            for field in expected_fields:
                assert field in row
            assert row["already_ordered"] is False

    def test_recommendation_quantity_calculation(self, client):
        """Test suggested quantity and line cost are derived from forecast and stock."""
        for row in client.get("/api/restock/recommendations").json():
            assert row["suggested_quantity"] == max(row["forecasted_demand"] - row["stock_on_hand"], 0)
            assert abs(row["line_cost"] - row["suggested_quantity"] * row["unit_cost"]) < 0.01

    def test_recommendation_stock_falls_back_to_current_demand(self, client):
        """Test stock comes from inventory when the SKU exists, otherwise from current demand."""
        rows = recommendations_by_sku(client)
        inventory = {item["sku"]: item for item in client.get("/api/inventory").json()}

        # PSU-501 is the only forecast SKU present in inventory.
        assert rows["PSU-501"]["stock_on_hand"] == inventory["PSU-501"]["quantity_on_hand"]
        assert rows["WDG-001"]["stock_on_hand"] == rows["WDG-001"]["current_demand"]

    def test_recommendation_urgency_order(self, client):
        """Test rows are ranked: increasing trends first, then largest shortfall."""
        data = client.get("/api/restock/recommendations").json()

        assert [row["urgency_rank"] for row in data] == list(range(1, len(data) + 1))
        trends = [row["trend"] for row in data]
        first_non_increasing = next(i for i, t in enumerate(trends) if t != "increasing")
        assert all(t != "increasing" for t in trends[first_non_increasing:])

    def test_recommendation_lead_times(self, client):
        """Test lead time matches the per-category table."""
        for row in client.get("/api/restock/recommendations").json():
            expected = main.LEAD_TIME_DAYS.get(row["category"], main.DEFAULT_LEAD_TIME_DAYS)
            assert row["lead_time_days"] == expected


class TestRestockOrders:
    """Test suite for /api/restock-orders."""

    def test_get_restock_orders_empty(self, client):
        """Test that no orders exist before one is placed."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restock_order(self, client):
        """Test placing an order computes total, lead time and expected delivery."""
        rows = recommendations_by_sku(client)
        payload = {
            "budget": 10000,
            "items": [
                {"sku": "WDG-001", "quantity": 10},   # Mechanical Components, 9 days
                {"sku": "SNR-420", "quantity": 5},    # Sensors, 10 days
            ],
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["id"] == "RST-0001"
        assert order["status"] == "Submitted"
        assert len(order["items"]) == 2

        expected_total = 10 * rows["WDG-001"]["unit_cost"] + 5 * rows["SNR-420"]["unit_cost"]
        assert abs(order["total_cost"] - expected_total) < 0.01

        # Lead time is the slowest item in the order.
        assert order["lead_time_days"] == max(rows["WDG-001"]["lead_time_days"], rows["SNR-420"]["lead_time_days"])
        submitted = datetime.fromisoformat(order["submitted_date"])
        assert date.fromisoformat(order["expected_delivery"]) == (submitted + timedelta(days=order["lead_time_days"])).date()

    def test_created_order_is_listed(self, client):
        """Test GET returns placed orders, newest first."""
        client.post("/api/restock-orders", json={"budget": 1000, "items": [{"sku": "WDG-001", "quantity": 1}]})
        client.post("/api/restock-orders", json={"budget": 1000, "items": [{"sku": "GSK-203", "quantity": 1}]})

        data = client.get("/api/restock-orders").json()
        assert [o["id"] for o in data] == ["RST-0002", "RST-0001"]

    def test_ordered_item_marked_in_recommendations(self, client):
        """Test already_ordered flips to true after an item is ordered."""
        client.post("/api/restock-orders", json={"budget": 1000, "items": [{"sku": "WDG-001", "quantity": 1}]})

        rows = recommendations_by_sku(client)
        assert rows["WDG-001"]["already_ordered"] is True
        assert rows["GSK-203"]["already_ordered"] is False

    def test_create_restock_order_over_budget(self, client):
        """Test that an order above the budget is rejected."""
        response = client.post("/api/restock-orders", json={"budget": 10, "items": [{"sku": "MTR-304", "quantity": 1}]})
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()
        assert client.get("/api/restock-orders").json() == []

    def test_create_restock_order_empty(self, client):
        """Test that an order with no items is rejected."""
        response = client.post("/api/restock-orders", json={"budget": 1000, "items": []})
        assert response.status_code == 400

    def test_create_restock_order_invalid_quantity(self, client):
        """Test that zero quantities are rejected."""
        response = client.post("/api/restock-orders", json={"budget": 1000, "items": [{"sku": "WDG-001", "quantity": 0}]})
        assert response.status_code == 400

    def test_create_restock_order_unknown_sku(self, client):
        """Test that an unknown SKU returns 404."""
        response = client.post("/api/restock-orders", json={"budget": 1000, "items": [{"sku": "NOPE-999", "quantity": 1}]})
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_restock_order_duplicate_sku(self, client):
        """Test that ordering an already-ordered SKU returns 409."""
        payload = {"budget": 1000, "items": [{"sku": "WDG-001", "quantity": 1}]}
        assert client.post("/api/restock-orders", json=payload).status_code == 201
        assert client.post("/api/restock-orders", json=payload).status_code == 409

    def test_create_restock_order_missing_fields(self, client):
        """Test that a malformed request fails Pydantic validation."""
        response = client.post("/api/restock-orders", json={"items": [{"sku": "WDG-001"}]})
        assert response.status_code == 422
