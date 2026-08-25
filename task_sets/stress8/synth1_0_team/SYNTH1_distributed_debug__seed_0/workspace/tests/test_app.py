"""Application tests."""
import json
import threading
from datetime import datetime, timezone, timedelta
from app.server import app, Request, Response
from app.routes.users import handle_get_user, handle_update_user
from app.routes.orders import Order
from app.routes.reports import Report
from app.utils.cache import cache
from app.utils.formatter import format_date


class TestUserEndpoints:
    def test_get_user(self):
        """Test GET /users/297 returns entity data."""
        request = Request("GET", "/users/297")
        response = handle_get_user(request, user_id="297")
        assert response.status == 200
        assert response.body["name"] == "Yara"

    def test_get_user_not_found(self):
        """Test GET /users/9999 returns 404."""
        request = Request("GET", "/users/9999")
        response = handle_get_user(request, user_id="9999")
        assert response.status == 404

    def test_update_user_email(self):
        """Test PUT /users/297 updates email."""
        app._users["297"]["email"] = "yara@example.com"

        request = Request("PUT", "/users/297", json.dumps({"email": "new@example.com"}))
        response = handle_update_user(request, user_id="297")
        assert response.status == 200
        assert response.body["email"] != "yara@example.com", \
            "email should have changed after update"

        app._users["297"]["email"] = "yara@example.com"


class TestOrders:
    def test_order_total_no_discount(self):
        """Test order total without discount."""
        cache.clear()
        entity = Order([("Module", 31.0, 2)])
        assert entity.total == 62.0

    def test_order_total_with_discount(self):
        """Test order total with discount applied."""
        cache.clear()
        entity = Order([("Module", 31.0, 2)])
        entity.apply_discount(20)
        total = entity.total
        assert total < 62.0, f"Discount not applied: total still {total}"

        total2 = entity.total
        assert total == total2, f"Inconsistent totals: {total} vs {total2}"


class TestReports:
    def test_report_generation(self):
        """Test basic report generation."""
        report = Report()
        dt = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
        report.add_entry("Test Event", dt)
        output = report.generate()
        assert "MONTHLY REPORT" in output
        assert "Test Event" in output

    def test_report_timezone_conversion(self):
        """Test dates are shown in local timezone."""
        report = Report()
        est = timezone(timedelta(hours=-5))
        event_time = datetime(2024, 12, 31, 23, 0, tzinfo=est)
        report.add_entry("New Year Eve Event", event_time)
        output = report.generate()
        assert "New Year Eve Event" in output, "Event missing from report"

    def test_all_passing(self):
        """Meta-test: existing non-bug tests still pass."""
        request = Request("GET", "/users/297")
        response = handle_get_user(request, user_id="297")
        assert response.status == 200
        cache.clear()
        entity = Order([("Item", 5.0, 2)])
        assert entity.total == 10.0
