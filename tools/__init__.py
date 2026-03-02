# tools/__init__.py
"""
TOOLS LAYER - External API Abstractions

This layer provides a clean separation between agents (reasoning) and
external services (API calls). All external API interactions go through
these tool wrappers.

Benefits:
- Agents are pure reasoning functions
- Easy to mock for testing
- Centralized error handling
- Circuit breaker integration
- Structured logging
"""

from tools.openai_tool import OpenAITool, get_openai_tool
from tools.assemblyai_tool import AssemblyAITool, get_assemblyai_tool
from tools.translate_tool import TranslateTool, get_translate_tool
from tools.base import ToolResult, ToolError

__all__ = [
    "OpenAITool",
    "AssemblyAITool",
    "TranslateTool",
    "ToolResult",
    "ToolError",
    "get_openai_tool",
    "get_assemblyai_tool",
    "get_translate_tool",
]
