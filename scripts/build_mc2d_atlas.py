#!/usr/bin/env python3
"""Сборка атласа тайлов MC2D: ресайз → один WebP + player.webp + atlas.json."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "block_tiles"
OUT_DIR = ROOT / "frontend" / "public" / "games" / "mc2d"

CELL = 32
# Индекс = Tile enum (AIR..TREE)
TILE_FILES: dict[int, str | None] = {
    0: None,
    1: "sand.jpg",
    2: "ground.png",
    3: "stone.jpg",
    4: "iron.png",
    5: "diamond.png",
    6: "grass_block.jpg",
    7: None,  # TREE — устаревший индекс; деревья — спрайты tree1–4.png
}


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"Missing source folder: {SRC}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atlas = Image.new("RGBA", (CELL * 8, CELL), (0, 0, 0, 0))
    for tid in range(8):
        fn = TILE_FILES[tid]
        if not fn:
            continue
        path = SRC / fn
        if not path.is_file():
            raise SystemExit(f"Missing file: {path}")
        im = Image.open(path).convert("RGBA")
        im = im.resize((CELL, CELL), Image.Resampling.LANCZOS)
        atlas.paste(im, (tid * CELL, 0), im)

    atlas_path = OUT_DIR / "atlas.webp"
    atlas.save(atlas_path, "WEBP", quality=82, method=6)
    meta = {"cell": CELL, "cols": 8, "tiles": ["air", "sand", "dirt", "stone", "iron", "diamond", "grass", "tree"]}
    (OUT_DIR / "atlas.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    pl_path = SRC / "player.png"
    if pl_path.is_file():
        pl = Image.open(pl_path).convert("RGBA")
        target_h = 48
        tw = max(1, int(round(pl.width * (target_h / pl.height))))
        pl = pl.resize((tw, target_h), Image.Resampling.LANCZOS)
        pl.save(OUT_DIR / "player.webp", "WEBP", quality=86, method=6)

    sz = atlas_path.stat().st_size
    print(f"Wrote {atlas_path} ({sz // 1024} KiB), {OUT_DIR / 'player.webp'}")


if __name__ == "__main__":
    main()
