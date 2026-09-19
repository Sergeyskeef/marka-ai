"""Bounded, cancellable OpenAI transcription subprocess. Never prints credentials."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat
import struct
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
MODEL = "gpt-4o-transcribe"
MAX_AUDIO = 2 * 1024 * 1024
MAX_RESPONSE = 48000


class APIError(ValueError):
    pass


def ogg_duration(data):
    """Bound one complete CRC-checked Opus stream before sending it to the API.

    Duration is derived from Opus packet timing, pre-skip and final granule,
    not from Telegram metadata. The API remains responsible for full decoding.
    """
    table = []
    for value in range(256):
        crc = value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
        table.append(crc)
    offset = sequence = packet_count = total_samples = pre_skip = last_samples = 0
    packet, serial, ended = bytearray(), None, False
    while offset < len(data):
        if ended or offset + 27 > len(data) or data[offset:offset + 5] != b"OggS\0":
            raise APIError("invalid_audio")
        flags = data[offset + 5]
        if flags & ~7 or bool(flags & 1) != bool(packet) or bool(flags & 2) != (sequence == 0):
            raise APIError("invalid_audio")
        granule, current_serial, current_sequence = struct.unpack_from("<QII", data, offset + 6)
        if serial is None:
            serial = current_serial
        if serial != current_serial or current_sequence != sequence:
            raise APIError("invalid_audio")
        header_end = offset + 27 + data[offset + 26]
        if header_end > len(data):
            raise APIError("invalid_audio")
        sizes = data[offset + 27:header_end]
        end = header_end + sum(sizes)
        if end > len(data):
            raise APIError("invalid_audio")
        page = bytearray(data[offset:end])
        expected = struct.unpack_from("<I", page, 22)[0]
        page[22:26] = b"\0" * 4
        crc = 0
        for value in page:
            crc = ((crc << 8) & 0xFFFFFFFF) ^ table[((crc >> 24) ^ value) & 255]
        if crc != expected:
            raise APIError("invalid_audio")
        cursor = header_end
        for size in sizes:
            packet.extend(data[cursor:cursor + size])
            cursor += size
            if len(packet) > 65536:
                raise APIError("invalid_audio")
            if size < 255:
                if packet_count == 0:
                    if len(packet) != 19 or packet[:8] != b"OpusHead" or packet[8] != 1 or packet[9] not in (1, 2) or packet[18] != 0:
                        raise APIError("invalid_audio")
                    pre_skip = struct.unpack_from("<H", packet, 10)[0]
                elif packet_count == 1:
                    if not packet.startswith(b"OpusTags"):
                        raise APIError("invalid_audio")
                else:
                    if not packet:
                        raise APIError("invalid_audio")
                    config, code = packet[0] >> 3, packet[0] & 3
                    samples = (120 << (config & 3)) if config >= 16 else (480 << (config & 1)) if config >= 12 else 480 * (1, 2, 4, 6)[config & 3]
                    frames = 1 if code == 0 else 2 if code in (1, 2) else (packet[1] & 63) if len(packet) >= 2 else 0
                    last_samples = samples * frames
                    if not 0 < last_samples <= 5760:
                        raise APIError("invalid_audio")
                    total_samples += last_samples
                    if total_samples > 60 * 48000 + pre_skip + 5760:
                        raise APIError("too_long")
                packet_count += 1
                packet.clear()
        ended = bool(flags & 4)
        sequence += 1
        offset = end
    if not ended or packet or packet_count < 3 or not total_samples - last_samples <= granule <= total_samples:
        raise APIError("invalid_audio")
    duration = (granule - pre_skip) / 48000
    if not 0 < duration <= 60:
        raise APIError("too_long" if duration > 60 else "invalid_audio")
    return duration


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise APIError("redirect_denied")


def read_key(path):
    """Use a dedicated owner-only file, never a key supplied by environment."""
    path = Path(path)
    try:
        if path.is_symlink():
            raise APIError("key_unavailable")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024:
                raise APIError("key_unavailable")
            if sys.platform == "linux" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise APIError("key_unavailable")
            key = stream.read(1025).decode("ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,512}", key):
            raise APIError("key_unavailable")
        return key
    except (OSError, UnicodeError):
        raise APIError("key_unavailable") from None


def request_audio(key_file, audio, *, opener=None):
    if not isinstance(audio, bytes) or not 64 <= len(audio) <= MAX_AUDIO:
        raise APIError("invalid_audio")
    duration = ogg_duration(audio)
    key = read_key(key_file)
    boundary = "marka-stt-" + secrets.token_hex(24)
    body = bytearray()
    for name, value in (("model", MODEL), ("response_format", "json"), ("stream", "false")):
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="voice.ogg"\r\nContent-Type: audio/ogg\r\n\r\n'.encode())
    body.extend(audio)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(ENDPOINT, bytes(body), method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "multipart/form-data; boundary=" + boundary,
        "Accept": "application/json", "User-Agent": "marka-ai/voice"})
    # Do not inherit HTTP(S)_PROXY, API base URL, cookies, or shared client state.
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=110) as response:
            if response.status != 200:
                raise APIError("service_unavailable")
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise APIError("invalid_response")
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get("text"), str):
            raise APIError("invalid_response")
        return {"text": value["text"], "engine": "openai", "model": MODEL, "duration_seconds": duration}
    except urllib.error.HTTPError as exc:
        # Raw service error bodies may repeat submitted data or request metadata.
        # They are deliberately neither read nor printed.
        exc.close()
        raise APIError({400: "invalid_audio", 401: "authentication_failed", 403: "access_denied",
                        413: "invalid_audio", 429: "rate_limit"}.get(exc.code, "service_unavailable")) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise APIError("network_error") from None
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, APIError):
            raise
        raise APIError("invalid_response") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = request_audio(args.key_file, sys.stdin.buffer.read(MAX_AUDIO + 1))
    except APIError as exc:
        result = {"error": str(exc)}
    except Exception:
        result = {"error": "service_unavailable"}
    payload = json.dumps(result, ensure_ascii=False).encode()
    if len(payload) + 1 > MAX_RESPONSE:
        payload = b'{"error":"invalid_response"}'
    sys.stdout.buffer.write(payload + b"\n")


if __name__ == "__main__":
    main()
