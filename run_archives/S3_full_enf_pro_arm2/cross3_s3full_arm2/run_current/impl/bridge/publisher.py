"""
Bridge publisher: sends translated messages to Service B's consumer.
"""
from __future__ import annotations
from service_b.schema import EventMessage, StatusMessage
from service_b.consumer import MessageConsumer
from bridge.translator import translate_event_streaming
from bridge.error_mapper import map_http_error, map_http_error_with_headers
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class BridgePublisher:
    """Fetches from Service A and publishes to Service B."""

    def __init__(self, consumer: MessageConsumer):
        self.consumer = consumer

    def publish_record(self, json_data: dict) -> None:
        """Translate and publish a single record."""
        try:
            msg = translate_event_streaming(json_data)
            self.consumer.consume(msg)
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            raise

    def publish_error(
        self, http_status: int, detail: str = "", headers: Optional[dict] = None
    ) -> None:
        """Map an HTTP error and publish as error status.

        Args:
            http_status: HTTP status code from Service A response
            detail: Human-readable error message
            headers: Optional HTTP response headers for enhanced error
                     propagation (e.g. Retry-After for 429)
        """
        if headers and http_status == 429:
            status_msg = map_http_error_with_headers(http_status, headers, detail)
        else:
            status_msg = map_http_error(http_status, detail)
        self.consumer.consume_error(status_msg)
