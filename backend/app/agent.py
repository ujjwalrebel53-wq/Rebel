"""Coding agent loop — Copilot API + tool execution."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.tools import WORKSPACE, execute_tool, tool_definitions

SYSTEM_PROMPT = f"""You are Rebel, an autonomous coding agent (similar to Cursor Agent).

Workspace root: {WORKSPACE}

You can read/write files, search code, run terminal commands, commit, push to GitHub, and open pull requests.

Rules:
- Make minimal, focused changes. Match existing project style.
- After editing code, run relevant tests or linters when appropriate.
- When the user asks to push to GitHub: git_commit → git_push → create_pull_request if needed.
- Explain briefly what you did after completing tasks.
- Never expose secrets; use .env for credentials.
"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.copilot_api_base.rstrip("/"),
        api_key=settings.copilot_api_key or "copilot",
    )


async def run_agent(
    messages: list[dict[str, Any]],
    max_turns: int = 25,
) -> AsyncIterator[dict[str, Any]]:
    """
    Yields events: {type: 'text'|'tool_start'|'tool_end'|'done'|'error', ...}
    """
    client = _client()
    history = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]

    for turn in range(max_turns):
        stream = await client.chat.completions.create(
            model=settings.copilot_model,
            messages=history,
            tools=tool_definitions(),
            tool_choice="auto",
            stream=True,
        )

        assistant_text = ""
        tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                assistant_text += delta.content
                yield {"type": "text", "content": delta.content}

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls[idx]["arguments"] += tc.function.arguments

        if not tool_calls:
            yield {"type": "done", "content": assistant_text}
            return

        # Build assistant message with tool calls for history
        formatted_tools = []
        for idx in sorted(tool_calls.keys()):
            tc = tool_calls[idx]
            formatted_tools.append(
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
            )

        history.append(
            {
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": formatted_tools,
            }
        )

        for idx in sorted(tool_calls.keys()):
            tc = tool_calls[idx]
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}

            yield {"type": "tool_start", "name": name, "arguments": args}
            result = execute_tool(name, args)
            yield {"type": "tool_end", "name": name, "result": result}

            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                }
            )

    yield {"type": "error", "content": "Max agent turns reached"}
