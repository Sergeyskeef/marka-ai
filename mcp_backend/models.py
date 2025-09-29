from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ExecResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    started_at: str
    finished_at: str
    duration_ms: int
    truncated: bool = False
    meta: Dict[str, Any] = {}

class ComposeCmdIn(BaseModel):
    cmd: str = Field(examples=["ps","up","down","restart"])
    service: Optional[str] = None
    flags: Optional[str] = None
    project_dir: Optional[str] = None
    project_name: Optional[str] = None

class ComposeLogsIn(BaseModel):
    service: str
    tail: int = 200
    since: Optional[str] = None
    follow: bool = False
    timestamps: bool = False
    project_dir: Optional[str] = "/srv/mark"
    flags: Optional[str] = None
    project_name: Optional[str] = None

class ContainerExecIn(BaseModel):
    service: str
    cmd: str
    workdir: Optional[str] = "/srv/mark"
    user: Optional[str] = None
    env: Optional[Dict[str,str]] = None
    timeout: int = 300
    tty: bool = False

class FileOpIn(BaseModel):
    path: str
    content: Optional[str] = None
    max_bytes: Optional[int] = None
