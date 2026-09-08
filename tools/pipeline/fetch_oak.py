#!/usr/bin/env python3
"""Fixed-source Crystal Oak intro portrait, native pixels and original colors.

OakSpeech selects POKEMON_PROF; TrainerPicPointers selects PokemonProfPic,
and TrainerPalettes selects gfx/trainers/oak.gbcpal. That palette is generated
from the PNG by the original Makefile/tools/gbcpal.c, with no Oak reversal.

    python3 tools/pipeline/fetch_oak.py --src /path/to/pokecrystal
    python3 tools/pipeline/fetch_oak.py --out /tmp/oak

The 56x56 source is packed at integer 2x (112x112), preserving all four source
indices. Source white stays index 3; the renderer skips it on the white page.
There is no interior-white recoloring. No UIA1 format change is required.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "sim"))

SOURCE_COMMIT = "7a7881d0d62e0ddbd82dcf10e7116807487ac651"
SOURCE_PATH = "gfx/trainers/oak.png"
SOURCE_SHA256 = "40e72de176670e4512af00990aebc2f9f7e9d1f552fe1c249ac9ee1e76eaed2e"
URL = f"https://raw.githubusercontent.com/pret/pokecrystal/{SOURCE_COMMIT}/{SOURCE_PATH}"

NATIVE_W = NATIVE_H = 56
SCALE = 2
OUT_W = OUT_H = NATIVE_W * SCALE

# Original Game Boy Color RGB5 palette, in engine shade order (black -> white).
# The original tools/gbcpal output is the reverse (white -> black).
OAK_RGB5 = ((0, 0, 0), (13, 16, 0), (24, 19, 11), (31, 31, 31))
OAK_PALETTE_RGB565 = tuple((r << 11) | (((g << 1) | (g >> 4)) << 5) | b
                           for r, g, b in OAK_RGB5)


def _display_hex(v: int) -> str:
    r, g, b = v >> 11, (v >> 5) & 63, v & 31
    return f"#{((r << 3) | (r >> 2)):02x}{((g << 2) | (g >> 4)):02x}{((b << 3) | (b >> 2)):02x}"


# Inspector uses the exact RGB565 channel expansion, matching the LCD path.
OAK_PALETTE = [_display_hex(v) for v in OAK_PALETTE_RGB565]
_PREV = {0: "██", 1: "▒▒", 2: "░░", 3: "  "}


def _verified(path: Path) -> str:
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != SOURCE_SHA256:
        raise ValueError(f"Oak source differs from pinned Crystal commit: {path}: {got}")
    return str(path)


def fetch(cache_dir: str = "/tmp/oak", src: str | None = None) -> str:
    """Use a hash-checked local checkout/cache, otherwise the immutable URL."""
    local = Path(src or "/tmp/pokecrystal") / SOURCE_PATH
    if src is not None or local.exists():
        return _verified(local)
    cache = Path(cache_dir) / f"crystal-{SOURCE_COMMIT[:12]}-oak.png"
    if cache.exists():
        return _verified(cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "ESP32-PokemonGo/fetch_oak"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError("Downloaded Oak PNG differs from pinned source")
    cache.write_bytes(data)
    return str(cache)


def oak_grid(cache_dir: str = "/tmp/oak", _stats: dict | None = None,
             src: str | None = None) -> list[list[int]]:
    """112x112 source indices, 0=black, 3=original white/transparent on white."""
    import convert_sprites as cs

    path = fetch(cache_dir, src)
    w, h, rows, _, _ = cs.read_png_full(path)
    if (w, h) != (NATIVE_W, NATIVE_H):
        raise ValueError(f"Oak source has unexpected dimensions {w}x{h}")
    color_to_shade = {color: shade for shade, color in enumerate(OAK_RGB5)}
    vals = [[color_to_shade[tuple(channel >> 3 for channel in pixel[:3])]
             for pixel in row] for row in rows]
    if _stats is not None:
        _stats.update(source=path, filled=0,
                      source_white=sum(v == 3 for row in vals for v in row))
    return [[v for v in row for _ in range(SCALE)]
            for row in vals for _ in range(SCALE)]


def oak_bytes(cache_dir: str = "/tmp/oak", src: str | None = None) -> bytes:
    import pixelart as pa
    return pa.to_2bpp(oak_grid(cache_dir, src=src))


def rgb565(hexstr: str) -> int:
    v = int(hexstr[1:], 16)
    r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="/tmp/oak", help="verified PNG cache directory")
    ap.add_argument("--src", help="local pinned pokecrystal checkout")
    ap.add_argument("--preview", action="store_true", help="also print the pixel grid")
    args = ap.parse_args()
    stats: dict = {}
    grid = oak_grid(args.out, stats, args.src)
    import pixelart as pa
    data = pa.to_2bpp(grid)
    print(f"Crystal {SOURCE_COMMIT}: {stats['source']}")
    print(f"oak: 56x56 -> 112x112, {len(data)} bytes; original white "
          f"{stats['source_white']} pixels preserved, none recolored")
    print("RGB565:", ", ".join(f"0x{v:04X}" for v in OAK_PALETTE_RGB565))
    print("sha256(oak 2bpp):", hashlib.sha256(data).hexdigest())
    if args.preview:
        for row in grid:
            print("".join(_PREV[v] for v in row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
