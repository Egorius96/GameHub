from __future__ import annotations

import hashlib
from pathlib import Path

from app.services.image_compress import ImageCompressionError, compress_image_bytes

MAX_CREATOR_UPLOAD_BYTES = 5 * 1024 * 1024  # вход до сжатия (как аватар — сжимается на сервере)


def _creator_file_prefix(game_key: str) -> str:
    return hashlib.sha256(game_key.encode("utf-8")).hexdigest()[:16]


def remove_previous_creator_files(dest_dir: Path, game_key: str) -> None:
    prefix = _creator_file_prefix(game_key)
    if not dest_dir.is_dir():
        return
    for p in dest_dir.glob(f"{prefix}.*"):
        try:
            p.unlink()
        except OSError:
            pass


def save_game_creator_photo(*, game_key: str, data: bytes, dest_dir: Path) -> str:
    """Сжатие как у аватара аккаунта (profile=\"avatar\")."""
    try:
        compressed, ext = compress_image_bytes(data, profile="avatar")
    except ImageCompressionError as e:
        raise ValueError("unsupported_image") from e

    dest_dir.mkdir(parents=True, exist_ok=True)
    remove_previous_creator_files(dest_dir, game_key)

    fname = f"{_creator_file_prefix(game_key)}.{ext}"
    path = dest_dir / fname
    path.write_bytes(compressed)
    return f"/game-creators/{fname}"
