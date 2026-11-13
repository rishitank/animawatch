"""AnimaWatch - MCP server that watches web animations like a human tester.

Measures dropped frames inside the page and finds visual artifacts with AI vision
(Gemini with your own key, or Ollama locally). Built with FastMCP.

Features:
- In-page frame timing (requestAnimationFrame, Long Animation Frames)
- Video and screenshot analysis for animation issues
- Production-ready with retry logic and circuit breakers
- Structured logging for observability
- Multiple AI providers (Gemini, Ollama)
"""

__version__ = "0.3.1"
__all__ = ["server", "browser", "vision", "config", "logging", "retry"]
