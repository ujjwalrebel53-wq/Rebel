from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Copilot / OpenAI-compatible API (e.g. copilot-api on localhost:4141)
    copilot_api_base: str = "http://127.0.0.1:4141/v1"
    copilot_api_key: str = "copilot"
    copilot_model: str = "gpt-4o"

    # Workspace root for file tools
    workspace_root: Path = Path(__file__).resolve().parents[2]

    # GitHub
    github_token: str = ""
    github_repo: str = ""  # owner/repo
    default_branch: str = "main"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


settings = Settings()
