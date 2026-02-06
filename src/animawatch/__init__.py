"""AnimaWatch - MCP server that watches web animations like a human tester.

Detects jank, stuttering, visual artifacts using AI vision (Gemini FREE or Ollama local).
Built with FastMCP leveraging the latest MCP spec capabilities.

Features:
- Video and screenshot analysis for animation issues
- Production-ready with retry logic and circuit breakers
- Structured logging for observability
- Multiple AI providers (Gemini, Ollama)
"""

__version__ = "0.3.1"
__all__ = ["server", "browser", "vision", "config", "logging", "retry"]
