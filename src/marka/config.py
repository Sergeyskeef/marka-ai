from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path
    token: str = ""
    model: str | None = None
    codex_binary: str = "codex"
    max_steps: int = 12
    daily_calls: int = 200
    provider_timeout: int = 180
    retention_days: int = 0
    sandbox_socket: str = ""
    task_max_steps: int = 48
    task_max_calls: int = 64
    task_max_seconds: int = 900
    semantic_search: bool = True
    timezone: str = "UTC"

    @property
    def workspace(self) -> Path:
        return self.data_dir / "workspace"

    @property
    def codex_home(self) -> Path:
        return self.data_dir / "codex"

    @property
    def voice_key_file(self) -> Path:
        return self.data_dir / "openai-stt.key"

    @property
    def database(self) -> Path:
        return self.data_dir / "marka.sqlite3"

    def prepare(self) -> None:
        if self.workspace.is_symlink() or self.codex_home.is_symlink():
            raise ValueError("Workspace and Codex home must not be symlinks")
        for directory in (self.data_dir, self.workspace, self.codex_home):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        if self.workspace.resolve() == self.data_dir.resolve():
            raise ValueError("Workspace must be separate from private state")
        if self.workspace.resolve().is_relative_to(self.codex_home.resolve()) or self.codex_home.resolve().is_relative_to(self.workspace.resolve()):
            raise ValueError("Workspace and credentials must not overlap")

    def save(self) -> None:
        self.prepare()
        value = {k: v for k, v in vars(self).items() if k != "data_dir"}
        target = self.data_dir / "settings.json"
        temporary = target.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
        target.chmod(0o600)

    @classmethod
    def load(cls, data_dir: str | Path | None = None) -> Settings:
        directory = Path(data_dir or os.environ.get("MARKA_DATA", Path.home() / ".marka")).expanduser().resolve()
        path = directory / "settings.json"
        value = json.loads(path.read_text("utf-8")) if path.exists() else {}
        allowed = set(cls.__dataclass_fields__) - {"data_dir"}
        settings = cls(directory, **{k: v for k, v in value.items() if k in allowed})
        settings.token = os.environ.get("TELEGRAM_BOT_TOKEN", settings.token)
        settings.codex_binary = os.environ.get("MARKA_CODEX_BIN", settings.codex_binary)
        settings.sandbox_socket = os.environ.get("MARKA_SANDBOX_SOCKET", settings.sandbox_socket)
        settings.model = os.environ.get("MARKA_MODEL", settings.model)
        settings.timezone = os.environ.get("MARKA_TIMEZONE", settings.timezone)
        from .scheduling import owner_timezone
        owner_timezone(settings.timezone)
        if not 1 <= settings.max_steps <= 50 or not 1 <= settings.daily_calls <= 10000:
            raise ValueError("Invalid work budget")
        if not 10 <= settings.provider_timeout <= 900 or settings.retention_days < 0:
            raise ValueError("Invalid timeout or retention")
        if not 1 <= settings.task_max_steps <= 500 or not 1 <= settings.task_max_calls <= 1000 or not 60 <= settings.task_max_seconds <= 86400:
            raise ValueError("Invalid total task budget")
        if type(settings.semantic_search) is not bool:
            raise ValueError("Invalid memory settings")
        settings.prepare()
        return settings
