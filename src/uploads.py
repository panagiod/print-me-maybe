"""Save product photos uploaded from the studio admin."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import UploadFile

from src.db import product_images_dir

_MAX_BYTES = 5 * 1024 * 1024
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _extension(upload: UploadFile, data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    ext = Path(upload.filename or "").suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if ext in _ALLOWED_EXT:
        return ".jpg" if ext == ".jpeg" else ext
    guessed = _TYPE_EXT.get((upload.content_type or "").split(";")[0].strip().lower(), "")
    if guessed:
        return guessed
    raise ValueError("Photo must be a JPG, PNG, WebP, or GIF")


def save_product_image(slug: str, upload: UploadFile) -> str:
    """Write an uploaded photo under DATA_DIR and return the public URL."""
    data = upload.file.read(_MAX_BYTES + 1)
    if not data:
        raise ValueError("Photo file is empty")
    if len(data) > _MAX_BYTES:
        raise ValueError("Photo must be 5 MB or smaller")
    ext = _extension(upload, data)
    filename = f"{slug}-{secrets.token_hex(4)}{ext}"
    dest = product_images_dir() / filename
    dest.write_bytes(data)
    return f"/media/products/{filename}"


def save_product_images(slug: str, uploads: list[UploadFile] | None) -> list[str]:
    """Save every non-empty upload and return public URLs in order."""
    urls: list[str] = []
    for upload in uploads or []:
        if upload is None or not getattr(upload, "filename", None):
            continue
        urls.append(save_product_image(slug, upload))
    return urls
