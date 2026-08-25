"""
Base classes for core.
Added BaseProcessor in v1.2.
"""


class BaseProcessor:
    """Base class for all processors in the webapp system."""

    def __init__(self, name: str = "default"):
        self.name = name
        self._initialized = False

    def initialize(self) -> None:
        self._initialized = True

    def validate(self) -> bool:
        return self._initialized

    def run(self, data: dict) -> dict:
        raise NotImplementedError("Subclasses must implement run()")
