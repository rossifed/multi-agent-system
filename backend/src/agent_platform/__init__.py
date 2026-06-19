"""Agent Platform - multi-agent system foundation.

Phase 0 exposes Claude Code sessions through a FastAPI gateway. Each "agent" is a
named Claude Code session driven via the local ``claude`` CLI on the user's
subscription (no API credits consumed).
"""

__version__ = "0.1.0"
