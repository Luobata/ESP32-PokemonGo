"""Build and drive the production firmware renderer on the desktop (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import struct
import subprocess
import tempfile
import time
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MAIN = ROOT / "firmware/main"
HOST = HERE / "host"
SOURCES = [
    "pokemon_names.c",
    "assets.c", "render.c", "nav.c", "combat.c", "trainer.c", "achievements.c", "play_achievements.c", "battle.c", "battle_escape.c", "battle_presentation.c", "pokemon_animation.c", "battle_fx.c", "battle_hud.c", "game_ui.c", "capture.c", "encounter.c", "exploration.c", "play_exploration.c",
    "nurture.c", "items.c", "party.c", "exp.c", "evolution.c", "opening.c", "transition.c",
    "play_idle.c", "play_enc.c", "play_battle.c", "play_capture.c",
    "play_care.c", "play_bag.c", "play_dex.c", "play_opening.c", "play_starter.c",
    "play_menu.c", "play_party.c", "play_trainer.c", "screen_idle.c", "audio.c", "music.c", "sound_mixer.c", "music_director.c",
]
ASSETS = ["gen1.bin", "gen1_front.bin", "gen1_back.bin", "palettes.bin",
          "font16.bin", "moves.bin", "ui.bin"]
FRAME_BYTES = 240 * 320 * 2


def build() -> tuple[Path, str]:
    """Hash source + real firmware assets; never reuse a stale preview binary."""
    def fingerprint():
        inputs = sorted(set([MAIN / s for s in SOURCES] + list(MAIN.glob("*.h")) +
                            list(HOST.rglob("*.h")) + list(HOST.glob("*.c")) +
                            [MAIN / "screen.c", Path(__file__).resolve(),
                             ROOT / "firmware/components/bsp/include/bsp_button.h"] +
                            [ROOT / "assets" / s for s in ASSETS]))
        digest = hashlib.sha256()
        for path in inputs:
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()[:20]
    version = fingerprint()
    out = ROOT / ".build/firmware-preview" / version
    exe = out / "preview"
    if exe.exists():
        return exe, version
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        tmp = Path(tmp)
        asm = []
        for name in ASSETS:
            symbol = "_binary_" + name.replace(".", "_")
            asset = str(ROOT / "assets" / name).replace("\\", "\\\\").replace('"', '\\"')
            asm += [".balign 4", f".global {symbol}_start", f".global {symbol}_end",
                    f"{symbol}_start:", f'.incbin "{asset}"', f"{symbol}_end:"]
        (tmp / "assets.S").write_text("\n".join(asm) + "\n")
        cc = shutil.which("cc")
        if not cc:
            raise RuntimeError("需要本机 C 编译器 cc 才能运行固件同源预览")
        command = [cc, "-std=gnu11", "-O2", "-DHOST_BUILD=1", "-Wall", "-Wextra",
                   "-Wno-unused-variable", "-Wno-unused-function", "-Wno-unused-parameter",
                   "-I", str(HOST / "include"), "-I", str(MAIN),
                   "-I", str(ROOT / "firmware/components/bsp/include"),
                   *[str(MAIN / s) for s in SOURCES], str(HOST / "screen_host.c"),
                   str(HOST / "runtime.c"), str(tmp / "assets.S"),
                   "-lz", "-lm", "-o", str(tmp / "preview")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError(result.stderr[-12000:])
        if fingerprint() != version:
            raise RuntimeError("构建期间源码或资产发生变化，请重新载入场景")
        out.mkdir(exist_ok=True)
        os.replace(tmp / "preview", exe)
    return exe, version


class Renderer:
    def __init__(self, executable: Path):
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        bufsize=0)
        self.updated = time.monotonic()

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()

    def _read(self, size: int, deadline: float) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise RuntimeError("固件预览超时")
            data = os.read(self.process.stdout.fileno(), size - len(chunks))
            if not data:
                error = self.process.stderr.read().decode(errors="replace")
                raise RuntimeError("固件预览进程退出：" + error[-2000:])
            chunks.extend(data)
        return bytes(chunks)

    def command(self, command: str) -> dict:
        self.updated = time.monotonic()
        self.process.stdin.write((command + "\n").encode("ascii"))
        self.process.stdin.flush()
        deadline = time.monotonic() + 15
        header = bytearray()
        while not header.endswith(b"\n") and len(header) < 120:
            header.extend(self._read(1, deadline))
        fields = header.decode("ascii").split()
        if len(fields) != 4 or fields[0] != "FRAME":
            raise RuntimeError("固件预览帧协议不匹配")
        return {"page": "P" + fields[1], "ms": int(fields[2]),
                "mismatch": int(fields[3]), "pixels": self._read(FRAME_BYTES, deadline)}

    def audio(self, samples: int) -> bytes:
        if not 0 <= samples <= 11025:
            raise ValueError("invalid audio sample count")
        self.updated = time.monotonic()
        self.process.stdin.write(f"audio {samples}\n".encode())
        self.process.stdin.flush()
        deadline = time.monotonic() + 15
        header = bytearray()
        while not header.endswith(b"\n") and len(header) < 50:
            header.extend(self._read(1, deadline))
        if header != f"AUDIO {samples}\n".encode():
            raise RuntimeError("audio frame protocol mismatch")
        return self._read(samples * 2, deadline)

    def inspect(self) -> dict:
        """Read fixture state for native integration tests, without changing it."""
        self.process.stdin.write(b"state\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 15
        line = bytearray()
        while not line.endswith(b"\n") and len(line) < 16384:
            line.extend(self._read(1, deadline))
        if not line.startswith(b"STATE ") or not line.endswith(b"\n"):
            raise RuntimeError("固件预览状态协议不匹配")
        return json.loads(line[6:])


def rgb888(pixels: bytes) -> bytes:
    """ST7789 wire RGB565BE, expanded exactly as tools/device/screenshot.py."""
    rgb = bytearray()
    for (v,) in struct.iter_unpack(">H", pixels):
        r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
        rgb.extend(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))
    return bytes(rgb)


def png(pixels: bytes) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rgb = rgb888(pixels)
    rows = b"".join(b"\0" + rgb[y * 720:(y + 1) * 720] for y in range(320))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", 240, 320, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    print(build()[0])
