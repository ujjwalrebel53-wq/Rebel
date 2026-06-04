# Rebel — AI Coding Agent (Cursor-style)

Rebel is a self-hosted coding agent: chat UI + file editor + autonomous tools (read/write code, terminal, **git commit**, **git push**, **GitHub PR**). It uses your **GitHub Copilot** subscription via any **OpenAI-compatible Copilot proxy**.

> **Note:** This is not a 1:1 clone of Cursor (proprietary IDE, indexing, cloud VMs, Bugbot, etc.). Rebel covers the core **agent loop**: chat → tools → code changes → GitHub.

## Features

| Feature | Status |
|--------|--------|
| Agent chat (streaming) | ✅ |
| Read / write / search files | ✅ |
| Run terminal commands | ✅ |
| Monaco code editor | ✅ |
| Git commit & push | ✅ |
| Create GitHub PR | ✅ |
| Copilot via OpenAI API | ✅ (your proxy) |
| Full Cursor IDE parity | ❌ |

## Quick start

### 1. Copilot API proxy

Rebel talks to an OpenAI-compatible endpoint. Pick one proxy and start it:

- [ericc-ch/copilot-api](https://github.com/ericc-ch/copilot-api) — `npx @ericc-ch/copilot-api` → `http://127.0.0.1:4141/v1`
- [yuchanns/copilot-openai-api](https://github.com/yuchanns/copilot-openai-api) — port `9191`

Authenticate with your GitHub account when the proxy asks (device flow).

### 2. Configure Rebel

```bash
cp .env.example .env
# Edit: COPILOT_API_BASE, WORKSPACE_ROOT, GITHUB_TOKEN, GITHUB_REPO
```

| Variable | Description |
|----------|-------------|
| `COPILOT_API_BASE` | Proxy URL, e.g. `http://127.0.0.1:4141/v1` |
| `COPILOT_MODEL` | e.g. `gpt-4o`, `claude-3.5-sonnet` (depends on proxy) |
| `WORKSPACE_ROOT` | Folder the agent can edit (your project) |
| `GITHUB_TOKEN` | PAT with `repo` scope |
| `GITHUB_REPO` | `owner/name` for PR creation |

### 3. Run

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

Open **http://localhost:5173**

Or manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload --port 8000

cd frontend && npm install && npm run dev
```

## Example prompts

- "Create a FastAPI health endpoint and write tests"
- "Fix the bug in `utils.py` and run pytest"
- "Commit with message 'Add login', push branch `feature/login`, open a PR to main"

## Architecture

```
Browser (React + Monaco)
    │ WebSocket /api
    ▼
FastAPI (agent loop + tools)
    │ OpenAI API
    ▼
Copilot proxy → GitHub Copilot
```

**Tools:** `read_file`, `write_file`, `list_directory`, `search_code`, `run_terminal`, `git_status`, `git_commit`, `git_push`, `create_pull_request`

## Security

- The agent can run shell commands and push code. Use only on projects you trust.
- Keep `.env` secret; never commit tokens.
- Restrict `WORKSPACE_ROOT` to a single project directory.

## License

MIT
