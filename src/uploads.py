"""Save product photos uploaded from the studio admin."""

from __future__ import annotations

import logging
import secrets
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from src.db import product_images_dir

_MAX_BYTES = 5 * 1024 * 1024
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
DISPLAY_MAX = 1600
THUMB_MAX = 400
JPEG_QUALITY = 85
logger = logging.getLogger(__name__)


def image_thumb_url(url: str) -> str:
    """Catalog/card URL: `-thumb` sibling for uploaded photos; static/SVG unchanged."""
    raw = (url or "").strip()
    if not raw:
        return raw
    if raw.startswith("/static/") or raw.lower().endswith(".svg"):
        return raw
    path = Path(raw)
    if path.stem.endswith("-thumb"):
        return raw
    parent = path.parent.as_posix()
    name = f"{path.stem}-thumb{path.suffix}"
    if parent in ("", "."):
        return name
    return f"{parent}/{name}"


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


def _fit(image: Image.Image, max_edge: int) -> Image.Image:
    if max(image.size) <= max_edge:
        return image
    fitted = image.copy()
    fitted.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return fitted


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def _open_image(data: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except UnidentifiedImageError as exc:
        raise ValueError("Photo must be a JPG, PNG, WebP, or GIF") from exc
    except OSError as exc:
        raise ValueError("Photo could not be read") from exc
    return ImageOps.exif_transpose(image) or image


def _save_jpeg(image: Image.Image, dest: Path) -> None:
    rgb = _to_rgb(image)
    rgb.save(dest, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)


def process_image_bytes(data: bytes) -> tuple[bytes, bytes]:
    """Return (display JPEG, thumb JPEG) after rotate, strip, and resize."""
    image = _open_image(data)
    display = _fit(image, DISPLAY_MAX)
    thumb = _fit(image, THUMB_MAX)
    display_buf = BytesIO()
    thumb_buf = BytesIO()
    _to_rgb(display).save(display_buf, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    _to_rgb(thumb).save(thumb_buf, format="JPEG", quality=80, optimize=True)
    return display_buf.getvalue(), thumb_buf.getvalue()


def save_product_image(slug: str, upload: UploadFile) -> str:
    """Write an uploaded photo under DATA_DIR and return the public display URL."""
    data = upload.file.read(_MAX_BYTES + 1)
    if not data:
        raise ValueError("Photo file is empty")
    if len(data) > _MAX_BYTES:
        raise ValueError("Photo must be 5 MB or smaller")
    _extension(upload, data)
    display_bytes, thumb_bytes = process_image_bytes(data)
    token = secrets.token_hex(4)
    filename = f"{slug}-{token}.jpg"
    thumb_name = f"{slug}-{token}-thumb.jpg"
    folder = product_images_dir()
    (folder / filename).write_bytes(display_bytes)
    (folder / thumb_name).write_bytes(thumb_bytes)
    return f"/media/products/{filename}"


def save_product_images(slug: str, uploads: list[UploadFile] | None) -> list[str]:
    """Save every non-empty upload and return public URLs in order."""
    urls: list[str] = []
    for upload in uploads or []:
        if upload is None or not getattr(upload, "filename", None):
            continue
        urls.append(save_product_image(slug, upload))
    return urls


def backfill_product_thumbs() -> None:
    """Write a sibling `-thumb` file for each existing upload that does not have one."""
    folder = product_images_dir()
    for path in folder.iterdir():
        if not path.is_file() or path.stem.endswith("-thumb"):
            continue
        if path.suffix.lower() not in _ALLOWED_EXT:
            continue
        thumb_path = path.with_name(f"{path.stem}-thumb{path.suffix}")
        if thumb_path.is_file():
            continue
        try:
            image = _open_image(path.read_bytes())
            thumb = _fit(image, THUMB_MAX)
            suffix = path.suffix.lower()
            if suffix in {".jpg", ".jpeg"}:
                _save_jpeg(thumb, thumb_path)
            elif suffix == ".png":
                thumb.save(thumb_path, format="PNG", optimize=True)
            elif suffix == ".webp":
                _to_rgb(thumb).save(thumb_path, format="WEBP", quality=80)
            else:
                _save_jpeg(thumb, path.with_name(f"{path.stem}-thumb.jpg"))
        except (ValueError, OSError) as exc:
            logger.warning("Skip thumb for %s: %s", path.name, exc)
