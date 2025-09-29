import os, shlex, subprocess, time, json, datetime
from typing import Optional, Dict, Any, List, Tuple
from models import ExecResult
import docker
import re

def _now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def _run_capture(argv: List[str], cwd: Optional[str]=None, timeout: Optional[int]=None) -> Tuple[int,str,str]:
    res = _run(argv, cwd=cwd, timeout=timeout)
    return res.exit_code, res.stdout, res.stderr

def _project_or_default(project_name: Optional[str], project_dir: Optional[str]) -> Optional[str]:
    if project_name:
        return project_name
    if project_dir:
        # basename каталога как дефолтное имя проекта
        return os.path.basename(os.path.abspath(project_dir))
    return None

def _run(cmd: List[str], cwd: Optional[str]=None, timeout: Optional[int]=None, env: Optional[Dict[str,str]]=None, max_output: int = 2_000_000) -> ExecResult:
    started = time.time()
    p = subprocess.Popen(cmd, cwd=cwd, env={**os.environ, **(env or {})}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        exit_code = 124
    else:
        exit_code = p.returncode
    # truncate big outputs
    truncated = False
    if len(out) > max_output:
        out = out[:max_output] + "\n[truncated]"
        truncated = True
    if len(err) > max_output:
        err = err[:max_output] + "\n[truncated]"
        truncated = True
    return ExecResult(
        stdout=out, stderr=err, exit_code=exit_code,
        started_at=_now_iso(),
        finished_at=_now_iso(),
        duration_ms=int((time.time()-started)*1000),
        truncated=truncated,
        meta={"cmd":" ".join(shlex.quote(c) for c in cmd), "cwd": cwd}
    )

def compose_cmd(cmd: str, service: Optional[str]=None, flags: Optional[str]=None, project_dir: Optional[str]=None, project_name: Optional[str]=None) -> ExecResult:
    """Выполняет docker compose команды через subprocess"""
    started = time.time()
    
    try:
        # docker compose GLOBAL_OPTS SUBCOMMAND [SERVICE]
        argv = ["docker", "compose"]
        if project_name:
            argv += ["-p", project_name]
        if flags:
            argv += shlex.split(flags)
        argv.append(cmd)
        if service:
            argv.append(service)
        
        res = _run(argv, cwd=project_dir, timeout=600)
        if res.exit_code == 0 and (res.stdout.strip() == "" or ("NAME" in res.stdout and res.stdout.count("\n") <= 1)):
            # fallback: показать контейнеры проекта по лейблу
            pname = _project_or_default(project_name, project_dir)
            if pname:
                code,out,err = _run_capture(["docker","ps","--filter",f"label=com.docker.compose.project={pname}","--format","{{.Names}}\t{{.Status}}\t{{.Image}}"], timeout=30)
                if code == 0 and out.strip():
                    res.stdout = "NAME\tSTATUS\tIMAGE\n" + out
        return res
    except Exception as e:
        return ExecResult(
            stdout="",
            stderr=str(e),
            exit_code=1,
            started_at=_now_iso(),
            finished_at=_now_iso(),
            duration_ms=int((time.time()-started)*1000),
            truncated=False,
            meta={"cmd": f"docker compose {cmd}", "cwd": project_dir, "error": str(e)}
        )

def compose_logs(service: str, tail: int=200, since: Optional[str]=None, follow: bool=False, timestamps: bool=False, project_dir: Optional[str]=None, project_name: Optional[str]=None) -> ExecResult:
    """Получает логи контейнера через subprocess"""
    started = time.time()
    
    try:
        if project_name:
            argv = ["docker", "compose", "-p", project_name, "logs", service, "--tail", str(tail)]
        else:
            argv = ["docker", "compose", "logs", service, "--tail", str(tail)]
        if since:
            argv += ["--since", since]
        if follow:
            argv.append("--follow")
        if timestamps:
            argv.append("--timestamps")
        
        res = _run(argv, cwd=project_dir, timeout=None if follow else 600)
        if res.exit_code != 0 or (res.exit_code == 0 and not res.stdout.strip()):
            # fallback: docker logs по container_name (если есть)
            pname = _project_or_default(project_name, project_dir)
            candidates = []
            if pname:
                code,out,err = _run_capture(["docker","ps","--filter",f"label=com.docker.compose.project={pname}","--format","{{.Names}}"], timeout=30)
                if code == 0:
                    candidates = [n for n in out.splitlines() if n.endswith(f"_{service}_1") or n==service]
            for name in ([service] + candidates):
                code,out,err = _run_capture(["docker","logs","--tail",str(tail),name] + (["--since",since] if since else []), timeout=60)
                if code == 0:
                    res.stdout = out
                    res.stderr = err
                    res.exit_code = 0
                    res.meta["fallback"] = "docker logs"
                    break
        return res
    except Exception as e:
        return ExecResult(
            stdout="",
            stderr=str(e),
            exit_code=1,
            started_at=_now_iso(),
            finished_at=_now_iso(),
            duration_ms=int((time.time()-started)*1000),
            truncated=False,
            meta={"cmd": f"docker compose logs {service}", "error": str(e)}
        )

def container_exec(service: str, cmd: str, workdir: Optional[str]="/", user: Optional[str]=None, env: Optional[Dict[str,str]]=None, timeout: int=300, tty: bool=False, project_dir: Optional[str]=None) -> ExecResult:
    """Выполняет команду в контейнере через subprocess"""
    started = time.time()
    
    try:
        argv = ["docker", "exec"]
        # без интерактива не используем -t; если нужен интерактив — выставим tty=True и добавим -t
        if tty:
            argv.append("-t")
        if workdir:
            argv += ["-w", workdir]
        if user:
            argv += ["-u", user]
        
        # Формируем команду с переменными окружения
        exec_cmd = cmd
        if env:
            export = " ".join(f'{k}={shlex.quote(v)}' for k,v in env.items())
            exec_cmd = f"{export} {cmd}"
        
        argv += [service, "sh", "-lc", exec_cmd]
        argv = [a for a in argv if a != ""]
        
        return _run(argv, cwd=project_dir, timeout=timeout)
    except Exception as e:
        return ExecResult(
            stdout="",
            stderr=str(e),
            exit_code=1,
            started_at=_now_iso(),
            finished_at=_now_iso(),
            duration_ms=int((time.time()-started)*1000),
            truncated=False,
            meta={"cmd": f"docker compose exec {service} {cmd}", "error": str(e)}
        )
