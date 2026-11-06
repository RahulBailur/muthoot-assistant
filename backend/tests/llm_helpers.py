"""A scripted stand-in for the LLM, so tests decide exactly what "the model" says."""

from dataclasses import dataclass, field
from typing import Any

from services.llm import LLMResponse, LLMUnavailable, Message, ToolCall, ToolSpec


@dataclass
class Call:
    system: str
    messages: list[Message]
    tools: list[ToolSpec]


@dataclass
class ScriptedLLM:
    """Answers agent requests from `script`, in order, and routing requests with `route`.

    A script entry is reply text, a list of tool calls as (name, args), or an exception.
    """

    script: list[str | list[tuple[str, dict[str, Any]]] | Exception] = field(default_factory=list)
    route: str = "general"
    name: str = "scripted"
    calls: list[Call] = field(default_factory=list)

    async def generate(
        self, system: str, messages: list[Message], tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        if system.startswith("Classify"):
            return LLMResponse(text=self.route, provider=self.name)
        self.calls.append(Call(system, list(messages), list(tools or [])))
        if not self.script:
            raise LLMUnavailable("script exhausted")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, str):
            return LLMResponse(text=step, provider=self.name)
        return LLMResponse(
            tool_calls=[ToolCall(name, args) for name, args in step], provider=self.name
        )

    def last_tool_result(self, tool: str) -> dict[str, Any] | None:
        """What the named tool returned, as the model last saw it."""
        for call in reversed(self.calls):
            for message in reversed(call.messages):
                if message.role == "tool" and message.tool_name == tool:
                    return message.tool_result
        return None
