"""Bounded image input and immutable private receipts, never model-selected paths."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import time
import zlib

from PIL import Image

from .redact import redact

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGES = 2
MAX_TOTAL_BYTES = 4 * 1024 * 1024
MAX_PIXELS = 8_000_000
MAX_DIMENSION = 4096


@dataclass(frozen=True, slots=True)
class ImageInput:
    data: bytes
    mime_type: str
    sha256: str
    width: int
    height: int

    @property
    def extension(self):
        return "png" if self.mime_type == "image/png" else "jpg"

    def receipt(self):
        return {"sha256": self.sha256, "bytes": len(self.data), "mime_type": self.mime_type,
                "width": self.width, "height": self.height}


def _dimensions(width, height):
    if not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION or width * height > MAX_PIXELS:
        raise ValueError("Image dimensions exceed 4096 per side or 8 million pixels")


def _png(data):
    position, dimensions, compressed, palette = 8, None, [], False
    ended, saw_idat, idat_closed = False, False, False
    while position < len(data):
        if position + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        size = int.from_bytes(data[position:position+4], "big")
        kind = data[position+4:position+8]
        end = position + size + 12
        if end > len(data) or not re.fullmatch(b"[A-Za-z]{4}", kind):
            raise ValueError("Invalid PNG chunk")
        payload = data[position+8:end-4]
        if zlib.crc32(kind + payload) & 0xffffffff != int.from_bytes(data[end-4:end], "big"):
            raise ValueError("PNG checksum mismatch")
        if dimensions is None and kind != b"IHDR":
            raise ValueError("PNG must begin with its image header")
        if kind == b"IHDR":
            if dimensions is not None or size != 13:
                raise ValueError("Invalid PNG header")
            width, height, depth, colour, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            _dimensions(width, height)
            if depth != 8 or colour not in {0, 2, 3, 4, 6} or compression or filtering or interlace:
                raise ValueError("Use a static non-interlaced 8-bit PNG or JPEG")
            dimensions = width, height, colour
        elif kind in {b"acTL", b"fcTL", b"fdAT"}:
            raise ValueError("Animated PNG is not supported")
        elif kind == b"PLTE":
            if saw_idat or palette or not 3 <= size <= 768 or size % 3:
                raise ValueError("Invalid PNG palette")
            palette = True
        elif kind == b"IDAT":
            if idat_closed:
                raise ValueError("PNG data chunks must be consecutive")
            saw_idat = True
            compressed.append(payload)
        elif kind == b"IEND":
            if size or end != len(data) or not saw_idat:
                raise ValueError("Invalid PNG ending")
            ended = True
            break
        elif kind[0] < 97:
            raise ValueError("Unsupported critical PNG chunk")
        if saw_idat and kind != b"IDAT":
            idat_closed = True
        position = end
    if not ended or dimensions is None:
        raise ValueError("Incomplete PNG image")
    width, height, colour = dimensions
    if colour == 3 and not palette:
        raise ValueError("Indexed PNG has no palette")
    row = width * {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour] + 1
    expected = row * height
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(b"".join(compressed), expected + 1)
    except zlib.error:
        raise ValueError("Corrupt PNG compressed data") from None
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("PNG decoded size does not match its header")
    if any(raw[offset] > 4 for offset in range(0, len(raw), row)):
        raise ValueError("Invalid PNG row filter")
    return width, height


def _jpeg(data):
    position, dimensions, scans = 2, None, 0
    while position < len(data):
        if data[position] != 255:
            raise ValueError("Invalid JPEG marker")
        while position < len(data) and data[position] == 255:
            position += 1
        if position >= len(data):
            break
        marker = data[position]
        position += 1
        if marker == 0xD9:
            if dimensions is None or not scans or position != len(data):
                raise ValueError("Invalid JPEG ending")
            return dimensions
        if marker in {0, 0xD8, 0x01, *range(0xD0, 0xD8)} or position + 2 > len(data):
            raise ValueError("Invalid JPEG structure")
        size = int.from_bytes(data[position:position+2], "big")
        end = position + size
        if size < 2 or end > len(data):
            raise ValueError("Truncated JPEG segment")
        payload = data[position+2:end]
        if marker in {0xC0, 0xC1, 0xC2}:
            if dimensions is not None or len(payload) < 6:
                raise ValueError("Invalid JPEG image header")
            depth, height, width, components = struct.unpack(">BHHB", payload[:6])
            if depth != 8 or components not in {1, 3, 4} or len(payload) != 6 + 3 * components:
                raise ValueError("Unsupported JPEG encoding")
            _dimensions(width, height)
            dimensions = width, height
        elif 0xC0 <= marker <= 0xCF and marker not in {0xC4, 0xC8, 0xCC}:
            raise ValueError("Unsupported JPEG frame type")
        if marker == 0xDA:
            if dimensions is None or len(payload) < 4 or payload[0] not in {1, 2, 3, 4} or len(payload) != 4 + 2 * payload[0]:
                raise ValueError("Invalid JPEG scan header")
            scans += 1
            if scans > 64:
                raise ValueError("JPEG has too many progressive scans")
            position, entropy = end, 0
            while position < len(data):
                if data[position] != 255:
                    position += 1
                    entropy += 1
                elif position + 1 < len(data) and data[position+1] in {0, *range(0xD0, 0xD8)}:
                    position += 2
                    entropy += 1
                else:
                    break
            if not entropy:
                raise ValueError("Empty JPEG scan")
        else:
            position = end
    raise ValueError("Incomplete JPEG image")


def validate_image(data: bytes, *, max_bytes=MAX_IMAGE_BYTES) -> ImageInput:
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_OUTPUT_IMAGE_BYTES:
        raise ValueError("Invalid image byte limit")
    if not isinstance(data, bytes) or not 1 <= len(data) <= max_bytes:
        raise ValueError(f"Each image must contain at most {max_bytes} bytes")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        width, height = _png(data)
        mime = "image/png"
    elif data.startswith(b"\xff\xd8"):
        width, height = _jpeg(data)
        mime = "image/jpeg"
    else:
        raise ValueError("Only PNG and JPEG images are supported")
    # Headers bound memory before invoking the real decoder. JPEG markers alone
    # do not prove that its entropy stream is decodable. Keep the original bytes
    # for provenance: validation never rewrites pixels, EXIF, or compression.
    try:
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as decoded:
            if decoded.size != (width, height) or getattr(decoded, "n_frames", 1) != 1:
                raise ValueError("Image decoder disagrees with its bounded header")
            decoded.load()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ValueError("Image pixel data is corrupt or unsupported") from None
    return ImageInput(data, mime, hashlib.sha256(data).hexdigest(), width, height)


def image_inputs(values) -> tuple[ImageInput, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > MAX_IMAGES:
        raise ValueError("At most two image inputs are supported")
    result = []
    total = 0
    for value in values:
        if not isinstance(value, ImageInput):
            raise ValueError("Image inputs must contain validated bytes, never filesystem paths")
        item = validate_image(value.data)
        if item != value:
            raise ValueError("Image input metadata does not match its bytes")
        total += len(item.data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Images exceed 4 MiB total")
        result.append(item)
    return tuple(result)


class MediaStore:
    def __init__(self, settings, store):
        self.store = store
        self.root = settings.data_dir / "media"
        if self.root.is_symlink():
            raise ValueError("Private media directory cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with store._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS media_uploads (source TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, "
                       "caption TEXT NOT NULL, images TEXT NOT NULL, created REAL NOT NULL)")

    def _path(self, receipt):
        digest, mime = receipt.get("sha256"), receipt.get("mime_type")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(mime, str) or mime not in {"image/png", "image/jpeg"}:
            raise ValueError("Invalid private image receipt")
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("Private media directory is unavailable or unsafe")
        target = self.root / (digest + (".png" if mime == "image/png" else ".jpg"))
        if target.is_symlink():
            raise ValueError("Private image must not be a symlink")
        return target

    def _read(self, receipt):
        if not isinstance(receipt, dict):
            raise ValueError("Invalid private image receipt")
        path = self._path(receipt)
        if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("Saved image is missing or oversized")
        with path.open("rb") as stream:
            image = validate_image(stream.read(MAX_IMAGE_BYTES + 1))
        if image.receipt() != receipt:
            raise ValueError("Saved image changed; resend the original image")
        return image

    def get(self, source: str, chat_id: int):
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM media_uploads WHERE source=?", (source,)).fetchone()
        if row is None:
            return None
        if row["chat_id"] != chat_id:
            raise ValueError("Image source belongs to a different conversation")
        receipts = json.loads(row["images"])
        if not isinstance(receipts, list) or not 1 <= len(receipts) <= MAX_IMAGES:
            raise ValueError("Invalid saved image collection")
        images = tuple(self._read(receipt) for receipt in receipts)
        return {"source": source, "chat_id": chat_id, "caption": row["caption"], "images": images,
                "receipts": receipts}

    def save(self, source: str, chat_id: int, caption: str, images):
        if not isinstance(source, str) or not re.fullmatch(r"telegram:\d+", source) or type(chat_id) is not int or chat_id <= 0:
            raise ValueError("Images need an original owner message source")
        if not isinstance(caption, str) or len(caption) > 4096:
            raise ValueError("Invalid image caption")
        images = image_inputs(images)
        if not images:
            raise ValueError("At least one image is required")
        clean, receipts = redact(caption), [image.receipt() for image in images]
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM media_uploads WHERE source=?", (source,)).fetchone()
            if old and (old["chat_id"] != chat_id or old["caption"] != clean or json.loads(old["images"]) != receipts):
                raise ValueError("An image source cannot be replaced by another upload")
            for image in images:
                path = self._path(image.receipt())
                if path.exists():
                    self._read(image.receipt())
                else:
                    descriptor, name = tempfile.mkstemp(prefix=".upload-", dir=self.root)
                    temporary = Path(name)
                    try:
                        with os.fdopen(descriptor, "wb") as stream:
                            stream.write(image.data)
                            stream.flush()
                            os.fsync(stream.fileno())
                        temporary.chmod(0o400)
                        temporary.replace(path)
                    finally:
                        if temporary.exists():
                            temporary.chmod(0o600)
                            temporary.unlink()
            db.execute("INSERT OR IGNORE INTO media_uploads VALUES(?,?,?,?,?)",
                       (source, chat_id, clean, json.dumps(receipts), time.time()))
        return self.get(source, chat_id)

    def for_job(self, job_id: str):
        with self.store._connect() as db:
            row = db.execute("SELECT source,chat_id,kind FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or row["kind"] != "image":
            return None
        upload = self.get(row["source"], row["chat_id"])
        if upload is None:
            raise ValueError("The image task lost its original upload receipt; resend the image")
        return upload
