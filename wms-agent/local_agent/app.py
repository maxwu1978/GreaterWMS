"""Compatibility wrapper for the local WMS agent ASGI app."""

from local_agent.server import app, main

__all__ = ["app", "main"]
