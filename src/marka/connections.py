"""Use installed credentials through fixed capabilities, never return their values."""
from __future__ import annotations

import asyncio
import copy
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.error
import urllib.request
import uuid

from .telegram import TelegramError
from .voice_api import APIError, MODEL, NoRedirect, read_key

CONNECTION_IDS = frozenset({"codex", "telegram", "openai_speech"})
CHECK_TTL = 60
CHECK_TIMEOUT = 25
MODEL_ENDPOINT = "https://api.openai.com/v1/models/gpt-4o-transcribe"
MAX_RESPONSE = 16384
_ERRORS = frozenset({"key_unavailable", "authentication_failed", "access_denied", "model_unavailable",
                     "rate_limit", "network_error", "redirect_denied", "invalid_response", "service_unavailable"})
_ACTIONS = {
    "codex": ("provider.complete",),
    "telegram": ("telegram.get_me", "telegram.webhook", "telegram.get_updates", "telegram.download",
                 "telegram.send_message", "telegram.send_document", "telegram.send_photo"),
    "openai_speech": ("voice.transcribe",),
}


def _speech_configured(path):
    """Presence is not successful authentication; do not read values for a list."""
    try:
        info = Path(path).lstat()
        return (stat.S_ISREG(info.st_mode) and 20 <= info.st_size <= 1024
                and (os.name == "nt" or (info.st_uid == os.getuid() and not info.st_mode & 0o077)))
    except (OSError, TypeError, ValueError):
        return False


def check_speech_key(key_file, *, opener=None):
    """One GET to a fixed model-metadata endpoint, with no upload or inference.

    A successful metadata read does not prove transcription write permission,
    available billing, or that a future audio transcription will succeed.
    """
    network_request = False
    try:
        if not _speech_configured(key_file):
            raise APIError("key_unavailable")
        key = read_key(key_file)
        request = urllib.request.Request(MODEL_ENDPOINT, method="GET", headers={
            "Authorization": "Bearer " + key, "Accept": "application/json",
            "User-Agent": "marka-ai/connections"})
        # No env proxy, cookies, configurable endpoint or credential-bearing
        # redirects. Errors intentionally discard bodies and provider IDs.
        opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        network_request = True
        with opener.open(request, timeout=12) as response:
            if response.status != 200:
                raise APIError("service_unavailable")
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise APIError("invalid_response")
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("object") != "model" or value.get("id") != MODEL:
            raise APIError("invalid_response")
        return {"ok": True, "error": None, "network_request": network_request, "details": {"model": MODEL, "model_visible": True,
                "transcription_verified": False, "billing_verified": False}}
    except urllib.error.HTTPError as exc:
        exc.close()
        error = {401: "authentication_failed", 403: "access_denied", 404: "model_unavailable",
                 429: "rate_limit"}.get(exc.code, "service_unavailable")
    except (urllib.error.URLError, TimeoutError, OSError):
        error = "network_error"
    except APIError as exc:
        error = str(exc) if str(exc) in _ERRORS else "service_unavailable"
    except (ValueError, UnicodeError, RecursionError):
        error = "invalid_response"
    except Exception:
        error = "service_unavailable"
    return {"ok": False, "error": error, "network_request": network_request, "details": {"model": MODEL, "model_visible": False,
            "transcription_verified": False, "billing_verified": False}}


class Connections:
    """Fixed reference registry owned by the protected bridge.

    In-flight checks survive a disconnected caller and share a result, preventing
    cancellation/retry loops from starting a fresh network check each time.
    """
    def __init__(self, *, provider, telegram, speech_key_file):
        self.provider, self.telegram = provider, telegram
        self.speech_key_file = speech_key_file
        self._cache = {}
        self._inflight = {}

    def _configured(self, connection):
        return _speech_configured(self.speech_key_file) if connection == "openai_speech" else True

    @staticmethod
    def _metadata(value, *, cached):
        return {**copy.deepcopy(value), "request_id": uuid.uuid4().hex, "cached": cached,
                "cache_ttl_seconds": CHECK_TTL, "secret_values_exposed": False, "inference_performed": False}

    def list(self):
        values = []
        for connection in ("codex", "telegram", "openai_speech"):
            cached = self._cache.get(connection)
            fresh = cached is not None and time.monotonic() - cached[0] < CHECK_TTL
            last = cached[1] if fresh else None
            values.append({"id": connection, "configured": self._configured(connection),
                           "available": last["ok"] if last else None,
                           "verification_scope": last["verification_scope"] if last else "not_checked",
                           "checked_at": last["checked_at"] if last else None,
                           "allowed_actions": list(_ACTIONS[connection]), "credential_storage": "protected_bridge",
                           "scope": "paired_owner_only" if connection == "telegram" else
                                    "owner_voice_only" if connection == "openai_speech" else "bounded_chatgpt_inference"})
        return {"request_id": uuid.uuid4().hex, "generated_at": time.time(), "connections": values,
                "secret_values_exposed": False, "read_only": True}

    async def check(self, connection):
        if not isinstance(connection, str) or connection not in CONNECTION_IDS:
            raise ValueError("Unknown managed connection")
        cached = self._cache.get(connection)
        if cached is not None and time.monotonic() - cached[0] < CHECK_TTL:
            return self._metadata(cached[1], cached=True)
        task = self._inflight.get(connection)
        shared = task is not None
        if task is None:
            task = asyncio.create_task(self._check_and_cache(connection))
            self._inflight[connection] = task
        return self._metadata(await asyncio.shield(task), cached=shared)

    async def _check_and_cache(self, connection):
        scope = {"codex": "local_login", "telegram": "bot_identity", "openai_speech": "model_metadata"}[connection]
        result = {"connection": connection, "configured": self._configured(connection),
                  "verification_scope": scope, "network_request": False}
        try:
            async with asyncio.timeout(CHECK_TIMEOUT):
                if connection == "codex":
                    raw = await self.provider.status()
                    authenticated = raw.get("authenticated") is True and raw.get("auth_method") == "chatgpt"
                    version = raw.get("version")
                    result.update(ok=authenticated, error=None if authenticated else "authentication_failed",
                                  details={"authenticated": authenticated, "auth_method": "chatgpt" if authenticated else "unavailable",
                                           "cli_version": version if isinstance(version, str) and len(version) <= 40
                                           and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9_.-]+)?", version) else None})
                elif connection == "telegram":
                    result["network_request"] = True
                    raw = await self.telegram.get_me()
                    if not isinstance(raw, dict) or raw.get("is_bot") is not True:
                        raise ValueError("Invalid bot identity")
                    details = {"is_bot": True}
                    username = raw.get("username")
                    if isinstance(username, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", username):
                        details["username"] = username
                    result.update(ok=True, error=None, details=details)
                else:
                    # If the overall wait expires before the bounded HTTP
                    # worker reports, do not claim that no request was sent.
                    result["network_request"] = None
                    result.update(await asyncio.to_thread(check_speech_key, self.speech_key_file))
        except TimeoutError:
            result.update(ok=False, error="check_timeout", details={})
        except TelegramError as exc:
            error = {401: "authentication_failed", 403: "access_denied", 429: "rate_limit"}.get(exc.code, "service_unavailable")
            result.update(ok=False, error=error, details={})
        except Exception:
            result.update(ok=False, error="service_unavailable", details={})
        finally:
            self._inflight.pop(connection, None)
        result["checked_at"] = time.time()
        self._cache[connection] = (time.monotonic(), result)
        return result
