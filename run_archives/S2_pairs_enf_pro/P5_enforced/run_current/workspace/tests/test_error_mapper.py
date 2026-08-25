from bridge.error_mapper import map_error


class TestErrorMapping:
    """Bug 5&6: 错误码映射"""

    def test_200_ok(self):
        code, msg = map_error(200)
        assert code == 0
        assert msg == "Success"

    def test_400_invalid_argument(self):
        code, msg = map_error(400)
        assert code == 3

    def test_404_not_found(self):
        """Bug 5: 404 必须映射为 NOT_FOUND (5)"""
        code, msg = map_error(404)
        assert code == 5
        assert "not found" in msg.lower()

    def test_429_resource_exhausted(self):
        """Bug 6: 429 必须映射为 RESOURCE_EXHAUSTED (8)"""
        code, msg = map_error(429)
        assert code == 8
        assert "too many" in msg.lower() or "exhausted" in msg.lower()

    def test_500_internal(self):
        code, msg = map_error(500)
        assert code == 13
