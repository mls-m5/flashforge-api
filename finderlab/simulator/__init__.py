"""Stateful, memory-only synthetic printer; never connects to hardware."""

from .server import MockConfig, MockPrinter

__all__ = ["MockConfig", "MockPrinter"]
