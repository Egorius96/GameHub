"""
Сжатие изображений при загрузке (общий слой для всех игр и профиля).

Приоритет — минимальный размер файла на выходе (~50–120 КБ для аватара).
На диск сохраняются только сжатые байты (WebP или JPEG fallback).
"""

from __future__ import annotations

import io
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

Profile = Literal["avatar", "general"]


class ImageCompressionError(ValueError):
    """Некорректное изображение или неподдерживаемый формат."""


_AVATAR_MAX_SIDE = 512
_AVATAR_TARGET_BYTES = 100 * 1024
_AVATAR_ABS_MAX = 256 * 1024

_GENERAL_MAX_SIDE = 1600
_GENERAL_TARGET_BYTES = 350 * 1024
_GENERAL_ABS_MAX = min(_GENERAL_TARGET_BYTES * 2, 900 * 1024)

# Плотный перебор качеств — выбирается вариант с минимальным числом байт
_QUALITIES_AVATAR = list(range(88, 9, -4))
_QUALITIES_GENERAL = list(range(90, 14, -5))


def _rgb_flatten(img: Image.Image) -> Image.Image:
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _webp_available(img: Image.Image) -> bool:
    buf = io.BytesIO()
    try:
        img.save(buf, format="WEBP", quality=50, method=4)
        return True
    except OSError:
        return False


def _thumb(img: Image.Image, max_side: int) -> Image.Image:
    if img.width <= max_side and img.height <= max_side:
        return img.copy()
    c = img.copy()
    c.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return c


def _encode_smallest_bytes(img: Image.Image, qualities: list[int], *, use_webp: bool) -> bytes:
    best: bytes | None = None
    best_len = 10**12
    for q in qualities:
        buf = io.BytesIO()
        try:
            if use_webp:
                img.save(buf, format="WEBP", quality=q, method=6)
            else:
                img.save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
        except OSError:
            continue
        raw = buf.getvalue()
        ln = len(raw)
        if ln < best_len:
            best_len = ln
            best = raw
    if best is None:
        raise ImageCompressionError("encode_failed")
    return best


def compress_image_bytes(
    data: bytes,
    *,
    profile: Profile = "avatar",
) -> tuple[bytes, str]:
    """
    Возвращает (сжатые байты, суффикс: \"webp\" или \"jpg\").
    """
    if not data:
        raise ImageCompressionError("empty_file")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ImageCompressionError("invalid_image") from e

    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
        img = img.copy()

    img = ImageOps.exif_transpose(img)
    rgb = _rgb_flatten(img)
    use_webp = _webp_available(rgb)

    if profile == "avatar":
        max_side = _AVATAR_MAX_SIDE
        target = _AVATAR_TARGET_BYTES
        abs_max = _AVATAR_ABS_MAX
        qualities = _QUALITIES_AVATAR
    else:
        max_side = _GENERAL_MAX_SIDE
        target = _GENERAL_TARGET_BYTES
        abs_max = _GENERAL_ABS_MAX
        qualities = _QUALITIES_GENERAL

    ext = "webp" if use_webp else "jpg"

    def once(side: int) -> tuple[bytes, str]:
        work = _thumb(rgb, side)
        raw = _encode_smallest_bytes(work, qualities, use_webp=use_webp)
        return raw, ext

    side = max_side
    out, out_ext = once(side)

    while len(out) > abs_max and side > 160:
        side = max(int(side * 0.82), 128)
        out, out_ext = once(side)

    attempts = 0
    while len(out) > target and attempts < 5 and side > 96:
        side = max(int(side * 0.88), 96)
        out, out_ext = once(side)
        attempts += 1

    return out, out_ext


def compressed_format_suffix() -> str:
    """Устарело; используйте второй элемент tuple из compress_image_bytes."""
    return "webp"
