"""Tests for audit.py — covering all boundary scenarios from planner1's plan."""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit


class TestLogEventHappyPath(unittest.TestCase):
    def test_config_changed_success(self):
        entry = audit.log_event(
            "config_changed",
            user_id="u1", config_key="theme",
            old_value="light", new_value="dark", user_agent="Mozilla/5.0",
        )
        self.assertEqual(entry["event_type"], "config_changed")
        self.assertIn("log_id", entry)
        self.assertIn("timestamp", entry)
        self.assertIn("signature", entry)
        self.assertEqual(audit.verify_log([entry]), [])

    def test_user_login_success(self):
        entry = audit.log_event(
            "user_login",
            user_id="u2", ip_address="192.168.1.1",
            success=True, correlation_id="corr-123",
        )
        self.assertEqual(entry["event_type"], "user_login")
        self.assertEqual(audit.verify_log([entry]), [])

    def test_report_accessed_success(self):
        entry = audit.log_event(
            "report_accessed",
            user_id="u3", report_id="rpt-001",
            report_type="quarterly", request_id="req-abc",
        )
        self.assertEqual(entry["event_type"], "report_accessed")
        self.assertEqual(audit.verify_log([entry]), [])

    def test_data_exported_success(self):
        entry = audit.log_event(
            "data_exported",
            user_id="u4", export_format="CSV", record_count=1500,
            destination="/exports/data.csv", user_agent="curl/7.88",
        )
        self.assertEqual(entry["event_type"], "data_exported")
        self.assertEqual(audit.verify_log([entry]), [])

    def test_payment_initiated_success(self):
        entry = audit.log_event(
            "payment_initiated",
            user_id="u5", amount="250.00", currency="USD",
            recipient_account="ACC-98765", session_id="sess-xyz",
        )
        self.assertEqual(entry["event_type"], "payment_initiated")
        self.assertEqual(audit.verify_log([entry]), [])


class TestLogEventErrors(unittest.TestCase):
    def test_unknown_event_type(self):
        with self.assertRaises(ValueError) as ctx:
            audit.log_event("unknown_event", foo="bar")
        self.assertIn("Unknown event_type", str(ctx.exception))

    def test_missing_fields_config_changed(self):
        with self.assertRaises(TypeError) as ctx:
            audit.log_event("config_changed", user_id="u1")
        self.assertIn("Missing required fields", str(ctx.exception))
        self.assertIn("config_key", str(ctx.exception))

    def test_missing_fields_user_login(self):
        with self.assertRaises(TypeError):
            audit.log_event("user_login", user_id="u1")

    def test_missing_fields_report_accessed(self):
        with self.assertRaises(TypeError):
            audit.log_event("report_accessed", user_id="u1")

    def test_missing_fields_data_exported(self):
        with self.assertRaises(TypeError):
            audit.log_event("data_exported", user_id="u1")

    def test_missing_fields_payment_initiated(self):
        with self.assertRaises(TypeError):
            audit.log_event("payment_initiated", user_id="u1")


class TestExtraFields(unittest.TestCase):
    def test_extra_field_accepted(self):
        entry = audit.log_event(
            "config_changed",
            user_id="u1", config_key="theme",
            old_value="light", new_value="dark",
            user_agent="UA", extra_field="bonus",
        )
        self.assertEqual(entry["extra_field"], "bonus")


class TestEmptyFields(unittest.TestCase):
    def test_empty_values_accepted(self):
        entry = audit.log_event(
            "config_changed",
            user_id="", config_key="k",
            old_value="", new_value="v", user_agent="",
        )
        self.assertEqual(entry["user_id"], "")


class TestGetLog(unittest.TestCase):
    def setUp(self):
        audit._log_store.clear()

    def test_empty(self):
        self.assertEqual(audit.get_log(), [])

    def test_returns_copy(self):
        audit.log_event("user_login", user_id="a", ip_address="1.1.1.1",
                         success=True, correlation_id="c1")
        audit.log_event("user_login", user_id="b", ip_address="2.2.2.2",
                         success=False, correlation_id="c2")
        logs = audit.get_log()
        self.assertEqual(len(logs), 2)
        logs.pop()
        self.assertEqual(len(audit.get_log()), 2)


class TestVerifyLog(unittest.TestCase):
    def setUp(self):
        audit._log_store.clear()

    def _entry(self):
        return audit.log_event("user_login", user_id="u",
                                ip_address="10.0.0.1", success=True,
                                correlation_id="c")

    def test_empty(self):
        self.assertEqual(audit.verify_log([]), [])

    def test_valid(self):
        self.assertEqual(audit.verify_log([self._entry(), self._entry()]), [])

    def test_missing_signature(self):
        e = self._entry()
        del e["signature"]
        self.assertEqual(audit.verify_log([e]), [0])

    def test_tampered_user_id(self):
        e = self._entry()
        e["user_id"] = "hacker"
        self.assertEqual(audit.verify_log([e]), [0])

    def test_replaced_signature(self):
        e = self._entry()
        e["signature"] = "a" * 64
        self.assertEqual(audit.verify_log([e]), [0])

    def test_mixed(self):
        e1, e2, e3, e4 = self._entry(), self._entry(), self._entry(), self._entry()
        e2["user_id"] = "tampered"
        del e4["signature"]
        self.assertEqual(audit.verify_log([e1, e2, e3, e4]), [1, 3])


class TestLogIdUniqueness(unittest.TestCase):
    def test_unique(self):
        ids = set()
        for _ in range(100):
            e = audit.log_event("config_changed", user_id="u",
                                 config_key="k", old_value="o",
                                 new_value="n", user_agent="ua")
            ids.add(e["log_id"])
        self.assertEqual(len(ids), 100)


class TestCanonicalJson(unittest.TestCase):
    def test_deterministic(self):
        d = {"event_type": "config_changed", "log_id": "fixed",
             "timestamp": "2026-01-01T00:00:00+00:00", "user_id": "u",
             "config_key": "k", "old_value": "o", "new_value": "n",
             "user_agent": "ua"}
        self.assertEqual(audit._compute_signature(d), audit._compute_signature(d))

    def test_order_invariant(self):
        self.assertEqual(
            audit._compute_signature({"a": 1, "b": 2, "c": 3}),
            audit._compute_signature({"c": 3, "a": 1, "b": 2}),
        )


class TestUnicode(unittest.TestCase):
    def test_unicode(self):
        e = audit.log_event("config_changed", user_id="用户",
                             config_key="配置", old_value="旧值",
                             new_value="新值", user_agent="浏览器")
        self.assertEqual(e["user_id"], "用户")
        self.assertEqual(audit.verify_log([e]), [])


class TestHmacKey(unittest.TestCase):
    def test_custom_key(self):
        d = {"a": 1, "b": 2}
        s1 = audit._compute_signature(d)
        os.environ["AUDIT_HMAC_KEY"] = "custom"
        try:
            s2 = audit._compute_signature(d)
        finally:
            del os.environ["AUDIT_HMAC_KEY"]
        self.assertNotEqual(s1, s2)


if __name__ == "__main__":
    unittest.main()
