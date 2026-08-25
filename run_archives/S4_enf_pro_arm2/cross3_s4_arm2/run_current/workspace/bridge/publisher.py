"""
Bridge publisher: sends translated messages to Service B's consumer.
"""
from __future__ import annotations
from service_b.schema import EventMessage, StatusMessage
from service_b.consumer import MessageConsumer
from bridge.translator import translate_event_streaming
from bridge.error_mapper import map_http_error
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

    def publish_error(self, http_status: int, detail: str = "") -> None:
        """Map an HTTP error and publish as error status."""
        status_msg = map_http_error(http_status, detail)
        self.consumer.consume_error(status_msg)
