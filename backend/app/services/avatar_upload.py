from __future__ import annotations

import hashlib
from pathlib import Path

from app.services.image_compress import ImageCompressionError, compress_image_bytes

MAX_AVATAR_UPLOAD_BYTES = 5 * 1024 * 1024  # вход до сжатия


def avatar_filename_for_user(username: str, ext: str) -> str:
    h = hashlib.sha256(username.encode("utf-8")).hexdigest()[:20]
    return f"{h}.{ext}"


def remove_previous_avatar_files(dest_dir: Path, username: str) -> None:
    """Удаляет старые файлы аватара этого пользователя (любое расширение)."""
    prefix = hashlib.sha256(username.encode("utf-8")).hexdigest()[:20]
    if not dest_dir.is_dir():
        return
    for p in dest_dir.glob(f"{prefix}.*"):
        try:
            p.unlink()
        except OSError:
            pass


def save_avatar_file(*, username: str, data: bytes, dest_dir: Path) -> str:
    """
    Сжимает изображение и сохраняет только результат (webp или jpg).
    Исходный файл на диск не попадает.
    """
    try:
        compressed, ext = compress_image_bytes(data, profile="avatar")
    except ImageCompressionError as e:
        raise ValueError("unsupported_image") from e

    dest_dir.mkdir(parents=True, exist_ok=True)
    remove_previous_avatar_files(dest_dir, username)

    fname = avatar_filename_for_user(username, ext)
    path = dest_dir / fname
    path.write_bytes(compressed)
    return f"/avatars/{fname}"
