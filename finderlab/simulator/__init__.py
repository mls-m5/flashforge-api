"""Stateful offline printer with memory-only virtual files/jobs; no hardware."""

from .server import MockConfig, MockPrinter

__all__ = ["MockConfig", "MockPrinter"]
