# main.py
"""FastAPI-ядро Марка: чат-инференс, долговременная память и песочница."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
import os
from pathlib import Path
from typing import Dict, Optional

from fastapi import Body, FastAPI, HTTPException
from langserve import add_routes
from rag.rag_chain import rag_chain
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams

# Константы
SANDBOX_DIR = Path("/sandbox")
COPY_ITEMS: list[str] = [
    "core_docs",
    "rag",
    "utils",
    "requirements.txt",
    "Dockerfile",
]

# Инициализация FastAPI
app = FastAPI(title="Mark AI", version="0.6")

# Функция: Убедиться, что класс Memory есть

def _ensure_memory_class() -> None:
    connection_params = ConnectionParams.from_params(
        http_host=os.getenv("WEAVIATE_HTTP_HOST", "weaviate"),
        http_port=int(os.getenv("WEAVIATE_HTTP_PORT", "8080")),
        http_secure=False,
        grpc_host=os.getenv("WEAVIATE_GRPC_HOST", "weaviate"),
        grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
        grpc_secure=False,
    )
    client = WeaviateClient(connection_params=connection_params)
    client.connect()
    schema = client.collections.list_all()
    if "Memory" in schema:
        return
    client.collections.create(
        name="Memory",
        vectorizer_config={"vectorizer": "text2vec-openai"},
        properties={
            "speaker": {"dataType": "string"},
            "text": {"dataType": "text"},
            "timestamp": {"dataType": "date"},
            "importance": {"dataType": "number"},
            "tags": {"dataType": "string[]"},
        },
    )

_ensure_memory_class()

# Хелперы

def _store_pair(question: str, answer: str, *, chat_id: int | None = None) -> Dict:
    connection_params = ConnectionParams.from_params(
        http_host=os.getenv("WEAVIATE_HTTP_HOST", "weaviate"),
        http_port=int(os.getenv("WEAVIATE_HTTP_PORT", "8080")),
        http_secure=False,
        grpc_host=os.getenv("WEAVIATE_GRPC_HOST", "weaviate"),
        grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
        grpc_secure=False,
    )
    client = WeaviateClient(connection_params=connection_params)
    client.connect()
    uid = hashlib.md5(f"{question}{answer}".encode()).hexdigest()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    payload = {
        "speaker": "user",
        "text": f"Q: {question}\nA: {answer}",
        "timestamp": timestamp,
        "importance": 0,
        "tags": [],
    }
    try:
        client.collections.get("Memory").data.insert(payload, uuid=uid)
    except Exception:
        return {"skipped": "duplicate", "id": uid}

    important = any(tok in question.lower() for tok in ("⚠", "❗", "error", "ошибка"))
    if important:
        exp_payload = {
            "summary": f"Q: {question}\nA: {answer}",
            "sourceIds": [uid],
            "createdAt": timestamp,
        }
        try:
            client.collections.get("Experience").data.insert(exp_payload)
        except Exception:
            pass

    return {"status": "stored", "id": uid, "important": important}


def _sync_to_sandbox() -> Dict:
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    for item in COPY_ITEMS:
        src = Path(__file__).parent / item
        dst = SANDBOX_DIR / item
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        if src.exists():
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    return {"synced": COPY_ITEMS, "sandbox_path": str(SANDBOX_DIR), "status": "ok"}


def _exec_in_sandbox(cmd: str, timeout: int = 15) -> Dict:
    if not cmd.strip():
        raise HTTPException(400, "empty command")
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=SANDBOX_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "command timeout")

    return {
        "cmd": cmd,
        "returncode": res.returncode,
        "stdout": res.stdout[-4000:],
        "stderr": res.stderr[-4000:],
    }

# LangServe /chat/invoke
add_routes(app, rag_chain, path="/chat")

# REST-эндпоинты

@app.post("/chat/ask")
def chat_ask(
    question: str = Body(..., embed=True),
    chat_id: int | None = Body(None, embed=True),
) -> Dict:
    answer = rag_chain(question, chat_id)
    meta = _store_pair(question, answer, chat_id=chat_id)
    return {"answer": answer, **meta}


@app.post("/chat/store")
def chat_store(
    question: str = Body(..., embed=True),
    answer: str = Body(..., embed=True),
    chat_id: int | None = Body(None, embed=True),
) -> Dict:
    return _store_pair(question, answer, chat_id=chat_id)


@app.post("/sandbox/sync")
def sandbox_sync() -> Dict:
    return _sync_to_sandbox()


@app.post("/sandbox/exec")
def sandbox_exec(command: str = Body(..., embed=True)) -> Dict:
    return _exec_in_sandbox(command)


@app.get("/ping")
def ping() -> Dict:
    return {"status": "ok"}
