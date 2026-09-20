"""Bounded, in-memory views of workspace images; originals are never rewritten."""
from __future__ import annotations

from dataclasses import dataclass
import io
import os
from pathlib import Path
import stat

from PIL import Image, ImageOps

from .media import ImageInput, MAX_IMAGE_BYTES, MAX_OUTPUT_IMAGE_BYTES, validate_image


@dataclass(frozen=True)
class InspectionImage:
    source: ImageInput
    image: ImageInput
    transformed: bool
    alpha_background: str | None = None

    def receipt(self):
        return {"source": self.source.receipt(),
                "analysis_image": {**self.image.receipt(), "derived": self.transformed,
                                   "lossy": self.transformed,
                                   "alpha_background": self.alpha_background},
                "original_preserved": True}


def prepare_image(path: Path) -> InspectionImage:
    """Validate before decoding and derive at most three bounded JPEG views."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("Image must be a regular workspace file without hard links")
        if not 0 < before.st_size <= MAX_OUTPUT_IMAGE_BYTES:
            raise ValueError("Workspace image must contain at most 10 MiB")
        raw = stream.read(MAX_OUTPUT_IMAGE_BYTES + 1)
        after = os.fstat(stream.fileno())
    if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
            or len(raw) != before.st_size):
        raise ValueError("Image changed during reading; inspect it again")
    source = validate_image(raw, max_bytes=MAX_OUTPUT_IMAGE_BYTES)
    if len(raw) <= MAX_IMAGE_BYTES:
        return InspectionImage(source, source, False)
    background = None
    with Image.open(io.BytesIO(raw), formats=["PNG", "JPEG"]) as decoded:
        with ImageOps.exif_transpose(decoded) as oriented:
            if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
                background = "white"
                with oriented.convert("RGBA") as rgba:
                    canvas = Image.new("RGB", rgba.size, "white")
                    with rgba.getchannel("A") as alpha:
                        canvas.paste(rgba, mask=alpha)
            else:
                canvas = oriented.convert("RGB")
            with canvas:
                for dimension, quality in ((2048, 85), (1536, 80), (1024, 75)):
                    canvas.thumbnail((dimension, dimension), Image.Resampling.LANCZOS)
                    output = io.BytesIO()
                    canvas.save(output, format="JPEG", quality=quality)
                    data = output.getvalue()
                    if len(data) <= MAX_IMAGE_BYTES:
                        return InspectionImage(source, validate_image(data), True, background)
    raise ValueError("Could not produce a bounded analysis image")
