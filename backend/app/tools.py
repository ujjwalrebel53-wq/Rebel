"""Agent tools: filesystem, terminal, git, GitHub."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

WORKSPACE = settings.workspace_root.resolve()


def _safe_path(rel: str) -> Path:
    p = (WORKSPACE / rel.lstrip("/")).resolve()
    if not str(p).startswith(str(WORKSPACE)):
        raise ValueError("Path escapes workspace")
    return p


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from the project workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path from workspace root"},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a file in the workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List files and folders under a path.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative directory, default '.'"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_code",
                "description": "Search file contents with a regex pattern (ripgrep-style).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "glob": {"type": "string", "description": "Optional glob e.g. *.py"},
                    },
                    "required": ["pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_terminal",
                "description": "Run a shell command in the workspace directory. Use for tests, installs, builds.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_status",
                "description": "Show git status and current branch.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_commit",
                "description": "Stage all changes and commit with a message.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                    },
                    "required": ["message"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_push",
                "description": "Push current branch to origin on GitHub.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "branch": {"type": "string", "description": "Branch name; uses current if omitted"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_pull_request",
                "description": "Open a GitHub pull request via API.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "head_branch": {"type": "string"},
                        "base_branch": {"type": "string"},
                    },
                    "required": ["title", "body", "head_branch"],
                },
            },
        },
    ]


def _run(cmd: list[str], timeout: int = 120) -> str:
    r = subprocess.run(
        cmd,
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        return f"exit {r.returncode}\n{out}".strip()
    return out.strip() or "(ok)"


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    try:
        if name == "read_file":
            p = _safe_path(arguments["path"])
            if not p.is_file():
                return f"Error: not a file: {arguments['path']}"
            text = p.read_text(encoding="utf-8", errors="replace")
            if len(text) > 50000:
                return text[:50000] + "\n... (truncated)"
            return text

        if name == "write_file":
            p = _safe_path(arguments["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(arguments["content"], encoding="utf-8")
            return f"Wrote {arguments['path']} ({len(arguments['content'])} bytes)"

        if name == "list_directory":
            rel = arguments.get("path") or "."
            p = _safe_path(rel)
            if not p.is_dir():
                return f"Error: not a directory: {rel}"
            entries = []
            for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if child.name.startswith(".") and child.name not in (".env.example",):
                    continue
                kind = "dir" if child.is_dir() else "file"
                entries.append(f"{kind}\t{child.relative_to(WORKSPACE)}")
            return "\n".join(entries) or "(empty)"

        if name == "search_code":
            pattern = arguments["pattern"]
            glob = arguments.get("glob", "*")
            try:
                rx = re.compile(pattern)
            except re.error as e:
                return f"Invalid regex: {e}"
            hits: list[str] = []
            for fp in WORKSPACE.rglob(glob.lstrip("*") if glob.startswith("**/") else glob):
                if not fp.is_file() or ".git" in fp.parts or "node_modules" in fp.parts:
                    continue
                try:
                    for i, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if rx.search(line):
                            rel = fp.relative_to(WORKSPACE)
                            hits.append(f"{rel}:{i}:{line[:200]}")
                            if len(hits) >= 80:
                                return "\n".join(hits) + "\n... (truncated)"
                except OSError:
                    continue
            return "\n".join(hits) if hits else "No matches"

        if name == "run_terminal":
            return _run(["bash", "-lc", arguments["command"]])

        if name == "git_status":
            return _run(["git", "status", "-sb"]) + "\n\n" + _run(["git", "branch", "--show-current"])

        if name == "git_commit":
            _run(["git", "add", "-A"])
            return _run(["git", "commit", "-m", arguments["message"]])

        if name == "git_push":
            branch = arguments.get("branch") or _run(["git", "branch", "--show-current"]).strip()
            return _run(["git", "push", "-u", "origin", branch])

        if name == "create_pull_request":
            return _create_pr(
                title=arguments["title"],
                body=arguments["body"],
                head=arguments["head_branch"],
                base=arguments.get("base_branch") or settings.default_branch,
            )

        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error: {e}"


def _create_pr(title: str, body: str, head: str, base: str) -> str:
    repo = settings.github_repo.strip()
    token = settings.github_token.strip()
    if not repo or not token:
        return "Error: set GITHUB_REPO (owner/name) and GITHUB_TOKEN in .env"
    url = f"https://api.github.com/repos/{repo}/pulls"
    payload = {"title": title, "body": body, "head": head, "base": base}
    with httpx.Client(timeout=30) as client:
        r = client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if r.status_code >= 400:
        return f"GitHub API error {r.status_code}: {r.text}"
    data = r.json()
    return json.dumps({"html_url": data.get("html_url"), "number": data.get("number")})
