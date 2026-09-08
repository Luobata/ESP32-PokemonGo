#!/usr/bin/env python3
"""Compare all 151 original front assets with actual native P3 screen pixels.

The oracle reads the committed FRNT/GEN1/PALS binaries and original upstream
PNG/anim.asm independently. The union of every played front frame fixes one
origin at top 30 / right 232; resting artwork keeps that origin after motion.
It does not import, extract, or call the firmware's scene layout helper or C
animation sampler. The native executable compiles the
actual play_battle.c/render.c/screen.c path; the check compares wire RGB565 values
before any PNG or browser color conversion.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/inspector"))
from native import Renderer, build, png  # noqa: E402
from pokemon_animation_oracle import COMMIT, load_original  # noqa: E402

SCREEN_W, SCREEN_H = 240, 320
ROI = (120, 30, 240, 160)  # Half-open: includes all three source-size classes.
VISIBLE_TOP, VISIBLE_RIGHT, SCALE = 30, 232, 2
BACKGROUND, TRANSPARENT = 0xFFFF, 3
SPECIES_IDS = set(range(1, 152))
ASSET_NAMES = ("gen1.bin", "gen1_front.bin", "palettes.bin")
EVIDENCE_SPECIES = (19, 74, 150)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_species(data: bytes) -> dict[int, dict]:
    require(len(data) >= 16, "gen1.bin: truncated header")
    magic, version, stride, count, pool_size = struct.unpack_from("<4sHHII", data)
    require((magic, version, stride, count) == (b"GEN1", 1, 32, 151),
            "gen1.bin: unsupported record format or incomplete species set")
    pool_start = 16 + stride * count
    require(pool_start + pool_size == len(data), "gen1.bin: inconsistent length")
    result = {}
    for species in sorted(SPECIES_IDS):
        record = data[16 + (species-1)*stride:16 + species*stride]
        name_offset = struct.unpack_from("<H", record, 20)[0]
        name_length = record[22]
        require(name_offset + name_length <= pool_size, f"#{species}: name outside string pool")
        name = data[pool_start+name_offset:pool_start+name_offset+name_length].decode("utf-8")
        # The full byte is authoritative. The old low-nibble mask was a bug.
        result[species] = {"name": name, "palette": record[23]}
    return result


def read_palettes(data: bytes) -> list[tuple[int, ...]]:
    require(len(data) >= 12, "palettes.bin: truncated header")
    magic, version, sets, colors, count = struct.unpack_from("<4sHHHH", data)
    require(magic == b"PALS" and version == 1 and 1 <= sets <= 256 and colors == 4 and count == 151,
            "palettes.bin: unsupported format or incomplete species set")
    require(len(data) == 12 + sets*2*colors*2 + count, "palettes.bin: inconsistent length")
    # Normal palettes are the first `sets` groups; shiny=0 in every boot command.
    return [struct.unpack_from("<4H", data, 12 + index*8) for index in range(sets)]


def read_fronts(data: bytes) -> dict[int, tuple[int, bytes]]:
    require(len(data) >= 8, "gen1_front.bin: truncated header")
    magic, version, segment_count = struct.unpack_from("<4sHH", data)
    require((magic, version, segment_count) == (b"FRNT", 1, 3), "gen1_front.bin: unsupported segments")
    base = 8 + segment_count*12
    require(len(data) >= base, "gen1_front.bin: truncated segment directory")
    sprites, sizes, ranges = {}, set(), []
    for segment in range(segment_count):
        size, per, count, offset = struct.unpack_from("<HHII", data, 8+segment*12)
        require(size in (40, 48, 56) and size not in sizes, "gen1_front.bin: invalid or duplicate size class")
        sizes.add(size)
        require(per == size*size//4 and 0 < count <= 151, "gen1_front.bin: invalid sprite stride/count")
        start, end = base+offset, base+offset+count*(2+per)
        require(base <= start < end <= len(data), "gen1_front.bin: segment outside file")
        ranges.append((start, end))
        cursor = start
        for _ in range(count):
            species = struct.unpack_from("<H", data, cursor)[0]
            require(species in SPECIES_IDS and species not in sprites,
                    f"gen1_front.bin: invalid or duplicate species {species}")
            sprites[species] = (size, data[cursor+2:cursor+2+per])
            cursor += 2+per
    cursor = base
    for start, end in sorted(ranges):
        require(start == cursor, "gen1_front.bin: overlapping, missing, or unaccounted segment bytes")
        cursor = end
    require(cursor == len(data), "gen1_front.bin: unaccounted trailing bytes")
    require(set(sprites) == SPECIES_IDS, f"gen1_front.bin: missing species {sorted(SPECIES_IDS-set(sprites))}")
    return sprites


def decode_and_trim(size: int, packed: bytes) -> tuple[list[list[int]], tuple[int, int, int, int], int]:
    # Decode bytes to a complete source image, then remove transparent rows and
    # columns. This oracle does not use source-layout code or firmware geometry.
    shades = [shade for byte in packed for shade in (byte >> 6, (byte >> 4) & 3, (byte >> 2) & 3, byte & 3)]
    require(len(shades) == size*size, "incorrect decoded image size")
    rows = [shades[y*size:(y+1)*size] for y in range(size)]
    used_rows = [y for y, row in enumerate(rows) if any(shade != TRANSPARENT for shade in row)]
    used_columns = [x for x, column in enumerate(zip(*rows)) if any(shade != TRANSPARENT for shade in column)]
    require(bool(used_rows) and bool(used_columns), "blank front sprite")
    left, top = used_columns[0], used_rows[0]
    right, bottom = used_columns[-1]+1, used_rows[-1]+1
    trimmed = [row[left:right] for row in rows[top:bottom]]
    opaque = sum(shade != TRANSPARENT for shade in shades)
    require(sum(shade != TRANSPARENT for row in trimmed for shade in row) == opaque,
            "trim discarded a nontransparent source pixel")
    return trimmed, (left, top, right, bottom), opaque


def expected_roi(trimmed: list[list[int]], palette: tuple[int, ...],
                 position: tuple[int, int]) -> tuple[list[int], tuple[int, int, int, int]]:
    left, top, right, bottom = ROI
    row_width = right-left
    result = [BACKGROUND] * (row_width*(bottom-top))
    width, height = len(trimmed[0])*SCALE, len(trimmed)*SCALE
    x0, y0 = position
    require(left <= x0 and x0+width <= right and top <= y0 and y0+height <= bottom,
            "visible sprite does not fit the isolated battle ROI")
    expanded_rows = []
    for source_row in trimmed:
        row = [color for shade in source_row
               for color in [BACKGROUND if shade == TRANSPARENT else palette[shade]]*SCALE]
        expanded_rows.extend([row]*SCALE)
    for y, row in enumerate(expanded_rows):
        offset = (y0-top+y)*row_width + x0-left
        result[offset:offset+width] = row
    return result, (x0, y0, x0+width, y0+height)


def verify_source_coverage(size: int, packed: bytes, origin: tuple[int, int], species: int) -> tuple[int, int]:
    """Allow clipped padding on any side; reject even one clipped opaque pixel.

    Inspect the full original source, independently of the trimmed image used
    by the ROI oracle. A negative drawing origin is valid when the affected
    source pixels are transparent (e.g. Diglett's 16 empty top rows).
    """
    require(len(packed) == size*size//4, f"#{species}: incomplete source canvas")
    opaque_preserved = transparent_clipped = 0
    for source_y in range(size):
        y0 = origin[1] + source_y*SCALE
        visible_h = max(0, min(SCREEN_H, y0+SCALE)-max(0, y0))
        for source_x in range(size):
            position = source_y*size+source_x
            shade = (packed[position//4] >> (6-(position%4)*2)) & 3
            x0 = origin[0] + source_x*SCALE
            visible_w = max(0, min(SCREEN_W, x0+SCALE)-max(0, x0))
            clipped = SCALE*SCALE-visible_w*visible_h
            if shade == TRANSPARENT:
                transparent_clipped += clipped
            else:
                require(clipped == 0,
                        f"#{species}: opaque source pixel ({source_x},{source_y}) loses {clipped} "
                        f"scaled pixels outside screen at ({x0},{y0})")
                opaque_preserved += SCALE*SCALE
    return opaque_preserved, transparent_clipped


def compare_frame(pixels: bytes, expected: list[int], species: int, name: str) -> None:
    require(len(pixels) == SCREEN_W*SCREEN_H*2, f"#{species}: wrong frame size")
    frame = struct.unpack(f">{SCREEN_W*SCREEN_H}H", pixels)
    left, top, right, bottom = ROI
    actual = [color for y in range(top, bottom) for color in frame[y*SCREEN_W+left:y*SCREEN_W+right]]
    if actual != expected:
        mismatch = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
        first = mismatch[0]
        x, y = left+first%(right-left), top+first//(right-left)
        raise AssertionError(f"#{species:03} {name}: {len(mismatch)} ROI pixel mismatches; first ({x},{y}) "
                             f"actual=0x{actual[first]:04X}, expected=0x{expected[first]:04X}")


def require_rejection(action, expected_reason: str, label: str) -> None:
    try:
        action()
    except AssertionError as error:
        require(expected_reason in str(error), f"{label}: rejected for an unexpected reason: {error}")
    else:
        raise AssertionError(f"{label}: negative control was incorrectly accepted")


def clipping_negative_controls(size: int, packed: bytes, bbox: tuple[int, int, int, int],
                               origin: tuple[int, int], species: int) -> list[str]:
    """Move real source artwork one destination pixel beyond each screen edge."""
    left, top, right, bottom = bbox
    shifted = {
        "left": (-left*SCALE-1, origin[1]),
        "top": (origin[0], -top*SCALE-1),
        "right": (SCREEN_W-right*SCALE+1, origin[1]),
        "bottom": (origin[0], SCREEN_H-bottom*SCALE+1),
    }
    for edge, displaced in shifted.items():
        require_rejection(lambda p=displaced: verify_source_coverage(size, packed, p, species),
                          "opaque source pixel", f"opaque clipping at {edge}")
    return [f"opaque source pixel clipped at {edge}" for edge in shifted]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path,
                        default=ROOT / "reports/evidence/firmware-preview-2026-09-07")
    parser.add_argument("--src", type=Path, default=Path('/tmp/pokecrystal'))
    args = parser.parse_args()
    originals, original_hashes = load_original(args.src)
    executable, version = build()
    blobs = {name: (ROOT/"assets"/name).read_bytes() for name in ASSET_NAMES}
    species_data = read_species(blobs["gen1.bin"])
    fronts = read_fronts(blobs["gen1_front.bin"])
    palettes = read_palettes(blobs["palettes.bin"])
    sizes, frames, details = Counter(), {}, {}
    opaque_pixels = transparent_clipped_pixels = raw_canvas_outside = 0
    outside_edges = Counter({edge: 0 for edge in ("left", "top", "right", "bottom")})
    raw_bounds, negative_controls = [], []
    bounds = []

    for species in sorted(SPECIES_IDS):
        item = species_data[species]
        require(item["palette"] < len(palettes), f"#{species}: palette byte 23 is out of range")
        size, packed = fronts[species]
        original = originals[species]
        require(original.size == size and original.packed(0) == packed,
                f'#{species}: FRNT base differs from pinned original PNG')
        trimmed, source_bbox, opaque = decode_and_trim(size, packed)
        union_left, union_top, union_right, union_bottom = original.bbox
        source_origin = (VISIBLE_RIGHT-union_right*SCALE, VISIBLE_TOP-union_top*SCALE)
        union = (source_origin[0]+union_left*SCALE, VISIBLE_TOP,
                 VISIBLE_RIGHT, source_origin[1]+union_bottom*SCALE)
        require(ROI[0] <= union[0] < union[2] <= ROI[2] and ROI[1] <= union[1] < union[3] <= ROI[3],
                f'#{species}: an original animation frame reaches the HUD or leaves the stage')
        l, t, r, b = source_bbox
        expected, visible = expected_roi(trimmed, palettes[item["palette"]],
                                         (source_origin[0]+l*SCALE, source_origin[1]+t*SCALE))
        # Relate the trimmed image back to the complete original source canvas.
        # Transparent margins may cross any screen edge; opaque pixels may not.
        raw_left, raw_top = source_origin
        raw_right = source_origin[0]+size*SCALE
        raw_bottom = source_origin[1]+size*SCALE
        raw_bounds.append((raw_left, raw_top, raw_right, raw_bottom))
        outside = {"left": raw_left < 0, "top": raw_top < 0,
                   "right": raw_right > SCREEN_W, "bottom": raw_bottom > SCREEN_H}
        raw_canvas_outside += int(any(outside.values()))
        outside_edges.update({edge: int(value) for edge, value in outside.items()})
        preserved, clipped_padding = verify_source_coverage(size, packed, source_origin, species)
        require(preserved == opaque*SCALE*SCALE, f"#{species}: full-source and trimmed opaque counts differ")
        transparent_clipped_pixels += clipped_padding
        require(0 <= visible[0] < visible[2] <= SCREEN_W and 0 <= visible[1] < visible[3] <= SCREEN_H,
                f"#{species}: opaque content is clipped by screen")

        renderer = Renderer(executable)
        try:
            frame = renderer.command(f"boot 3 25 12 {species} 3 1 0")
            require(frame["page"] == "P3", f"#{species}: boot did not enter actual P3")
            # Original species scripts have different lengths; the 720 ms
            # slide is followed by a separate entrance-motion phase.
            for _ in range(100):
                phase = renderer.inspect()['presentation']['phase']
                if phase == 'choice':
                    break
                require(phase in ('entry', 'entrance-motion'), f'#{species}: unexpected entry phase {phase}')
                frame = renderer.command('tick 60')
            else:
                raise AssertionError(f'#{species}: entry/motion did not settle')
            require(renderer.inspect()['presentation']['wild_frame'] == 0,
                    f'#{species}: original motion did not restore its base frame')
            compare_frame(frame["pixels"], expected, species, item["name"])
            if not negative_controls:
                negative_controls = clipping_negative_controls(size, packed, source_bbox, source_origin, species)
                # Remove one visible destination pixel from an actual native
                # frame, proving the RGB565 comparison still detects data loss.
                at = next(i for i, color in enumerate(expected) if color != BACKGROUND)
                x, y = ROI[0]+at%(ROI[2]-ROI[0]), ROI[1]+at//(ROI[2]-ROI[0])
                corrupted = bytearray(frame["pixels"])
                struct.pack_into(">H", corrupted, (y*SCREEN_W+x)*2, BACKGROUND)
                require_rejection(lambda: compare_frame(bytes(corrupted), expected, species, item["name"]),
                                  "ROI pixel mismatches", "removed native sprite pixel")
                negative_controls.append("one visible native RGB565 sprite pixel removed")
            if species in EVIDENCE_SPECIES:
                frames[species] = frame["pixels"]
        finally:
            renderer.close()
        sizes[size] += 1
        opaque_pixels += opaque*SCALE*SCALE
        bounds.append(visible)
        if species in (*EVIDENCE_SPECIES, 50, 81):
            details[str(species)] = {"name": item["name"], "source_size": size,
                "source_bbox": source_bbox, "source_origin": source_origin,
                "original_motion_union": union, "original_duration_ticks": len(original.ticks),
                "visible_bbox": visible, "normal_palette": item["palette"],
                "opaque_source_pixels": opaque, "raw_canvas_right": raw_right,
                "raw_canvas_bbox": (raw_left, raw_top, raw_right, raw_bottom),
                "transparent_scaled_pixels_clipped": clipped_padding}

    require(all((ROOT/"assets"/name).read_bytes() == data for name, data in blobs.items()),
            "assets changed during comparison; rerun against a stable build")
    _, final_version = build()
    require(final_version == version, "firmware changed during comparison; rerun against a stable build")
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    for species, pixels in frames.items():
        (args.evidence_dir/f"aligned-{species}.png").write_bytes(png(pixels))
    summary = {
        "build": version, "species": len(fronts), "source_size_counts": dict(sorted(sizes.items())),
        "normal_palette_sets": len(palettes), "roi_half_open": ROI,
        "compared_rgb565_pixels": len(fronts)*(ROI[2]-ROI[0])*(ROI[3]-ROI[1]),
        "opaque_scaled_pixels_preserved": opaque_pixels,
        "visible_bounds_union": [min(v[0] for v in bounds), min(v[1] for v in bounds),
                                  max(v[2] for v in bounds), max(v[3] for v in bounds)],
        "transparent_canvas_outside_screen": raw_canvas_outside,
        "transparent_canvas_outside_edges": dict(outside_edges),
        "transparent_scaled_pixels_clipped": transparent_clipped_pixels,
        "raw_canvas_bounds_union": [min(v[0] for v in raw_bounds), min(v[1] for v in raw_bounds),
                                    max(v[2] for v in raw_bounds), max(v[3] for v in raw_bounds)],
        "transparent_canvas_beyond_right": outside_edges["right"],
        "maximum_raw_canvas_right": max(v[2] for v in raw_bounds),
        "negative_controls_rejected": negative_controls,
        "asset_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in blobs.items()},
        "original_animation_commit": COMMIT, "original_source_sha256": original_hashes,
        "examples": details, "evidence": str(args.evidence_dir.resolve()),
    }
    (args.evidence_dir/"aligned-layout.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, ValueError, RuntimeError, struct.error) as error:
        print(f"battle layout verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
