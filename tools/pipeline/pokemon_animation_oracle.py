"""Independent upstream PNG/ASM oracle for front-motion and page-layout tests.

Uses Pillow (not the converter PNG decoder), the pinned upstream gbcpal C tool,
and a per-tick VM (not the converter's flattened-run interpreter). No generated
atlas, manifest, C sampler or firmware geometry supplies expected frame data.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from PIL import Image

COMMIT = '7a7881d0d62e0ddbd82dcf10e7116807487ac651'
WHITE = (31, 31, 31)


@dataclass
class OriginalMotion:
    name: str
    size: int
    frames: list[list[tuple[int, int, int]]]
    normal_gbc: list[tuple[int, int, int]]
    shiny_gbc: list[tuple[int, int, int]]
    ticks: list[int]
    bbox: tuple[int, int, int, int]  # half-open, in source pixels

    def packed(self, frame: int) -> bytes:
        shades = [3 - self.normal_gbc.index(color) for color in self.frames[frame]]
        return bytes((shades[i] << 6) | (shades[i+1] << 4) |
                     (shades[i+2] << 2) | shades[i+3] for i in range(0, len(shades), 4))


def rgb565(c: tuple[int, int, int]) -> int:
    red, green, blue = c
    return red * 2048 + (green * 2 + green // 16) * 32 + blue


def original_ticks(text: str, frame_count: int) -> list[int]:
    instructions = []
    for raw in text.splitlines():
        code = raw.partition(';')[0].strip()
        if not code:
            continue
        instruction, *arguments = re.split(r'[\s,]+', code)
        operands = [int(arg[1:], 16) if arg.startswith('$') else int(arg, 10) for arg in arguments]
        expected = {'frame': 2, 'setrepeat': 1, 'dorepeat': 1, 'endanim': 0}
        if instruction not in expected or len(operands) != expected[instruction]:
            raise AssertionError(f'unknown original instruction: {code}')
        instructions.append((instruction, operands))
    pointer = repeats = wait = current = 0
    frames = []
    while len(frames) < 65536:
        if wait:
            frames.append(current)
            wait -= 1
            continue
        for _ in range(10000):
            if not 0 <= pointer < len(instructions):
                raise AssertionError('source script branches out of bounds')
            instruction, args = instructions[pointer]
            pointer += 1
            if instruction == 'endanim':
                return frames
            if instruction == 'frame':
                current, duration = args
                if not 0 <= current < frame_count or not 1 <= duration <= 255:
                    raise AssertionError('invalid source frame/wait')
                wait = duration - 1
                frames.append(current)
                break
            if instruction == 'setrepeat':
                repeats = args[0]
                continue
            if repeats:
                repeats -= 1
            if repeats:
                pointer = args[0]
                continue
            # .DoRepeat returns after an exhausted counter, without changing
            # the graphic. This adds one displayed tick, not another branch.
            frames.append(current)
            break
        else:
            raise AssertionError('non-yielding original animation script')
    raise AssertionError('unterminated original animation script')


def load_original(src: Path) -> tuple[dict[int, OriginalMotion], dict[str, str]]:
    listing = subprocess.check_output(['git', '-C', str(src), 'ls-tree', '-r', COMMIT], text=True)
    blobs = {line.split('\t', 1)[1]: line.split()[2] for line in listing.splitlines()}
    hashes = {}

    def pinned(path: str) -> bytes:
        content = (src / path).read_bytes()
        git_hash = hashlib.sha1(f'blob {len(content)}\0'.encode() + content).hexdigest()
        if blobs.get(path) != git_hash:
            raise AssertionError(f'original source differs from {COMMIT}: {path}')
        hashes[path] = hashlib.sha256(content).hexdigest()
        return content

    names = re.findall(r'INCBIN "gfx/pokemon/([^/]+)/normal\.gbcpal", middle_colors',
                       pinned('data/pokemon/palettes.asm').decode())[:151]
    if len(names) != 151:
        raise AssertionError('missing original species palette mapping')
    reverse = set(re.findall(r'gfx/pokemon/([^/]+)/normal\.gbcpal: tools/gbcpal \+= --reverse',
                             pinned('Makefile').decode()))
    pinned('macros/scripts/pic_anims.asm')
    pinned('engine/gfx/pic_animation.asm')
    motions = {}
    with tempfile.TemporaryDirectory(prefix='original-front-oracle-') as name:
        directory = Path(name)
        for filename in ('gbcpal.c', 'common.h'):
            (directory / filename).write_bytes(pinned('tools/' + filename))
        executable = directory / 'gbcpal'
        subprocess.run(['cc', '-std=c17', '-O2', str(directory / 'gbcpal.c'), '-o', str(executable)],
                       check=True, capture_output=True)
        for species, slug in enumerate(names, 1):
            inputs, front_pixels, size = [], [], 0
            for view in ('front', 'back'):
                path = f'gfx/pokemon/{slug}/{view}.png'
                pinned(path)
                with Image.open(src / path) as picture:
                    width, height = picture.size
                    if width not in (40, 48, 56) or height % width:
                        raise AssertionError(f'{path}: invalid original frame canvas')
                    rgba = list(picture.convert('RGBA').get_flattened_data())
                    if any(pixel[3] != 255 for pixel in rgba):
                        raise AssertionError(f'{path}: unsupported source alpha')
                    colors = [tuple(channel >> 3 for channel in pixel[:3]) for pixel in rgba]
                    palette = directory / f'{view}.gbcpal'
                    palette.write_bytes(b''.join(struct.pack('<H', r + (g << 5) + (b << 10))
                                                  for r, g, b in sorted(set(colors))))
                    inputs.append(palette)
                    if view == 'front':
                        size, front_pixels = width, colors
            palette_path = directory / 'normal.gbcpal'
            command = [str(executable)] + (['--reverse'] if slug in reverse else [])
            subprocess.run(command + [str(palette_path), *(str(p) for p in inputs)],
                           check=True, capture_output=True)
            values = struct.unpack('<4H', palette_path.read_bytes())
            normal = [(value & 31, (value >> 5) & 31, (value >> 10) & 31) for value in values]
            shiny_text = pinned(f'gfx/pokemon/{slug}/shiny.pal').decode()
            shiny = [WHITE, *(tuple(map(int, colors)) for colors in
                              re.findall(r'\bRGB\s+(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', shiny_text)), (0, 0, 0)]
            if len(shiny) != 4:
                raise AssertionError('invalid original shiny palette')
            squares = [front_pixels[i:i + size*size] for i in range(0, len(front_pixels), size*size)]
            sequence = original_ticks(pinned(f'gfx/pokemon/{slug}/anim.asm').decode(), len(squares))
            used = {0, *sequence}
            points = [(i % size, i // size) for frame in used
                      for i, color in enumerate(squares[frame]) if color != WHITE]
            bbox = (min(x for x, _y in points), min(y for _x, y in points),
                    max(x for x, _y in points) + 1, max(y for _x, y in points) + 1)
            motions[species] = OriginalMotion(slug, size, squares, normal, shiny, sequence, bbox)
    return motions, hashes
