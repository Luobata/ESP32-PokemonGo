#!/usr/bin/env python3
"""Package the existing IDF build; never reads or writes a connected device."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'firmware/build'
OUT = ROOT / 'release/community'
OUT.mkdir(parents=True, exist_ok=True)
IMAGES = [(0, 'bootloader/bootloader.bin', 'bootloader/bootloader.bin'),
          (0x8000, 'partition_table/partition-table.bin', 'partition_table/partition-table.bin'),
          (0x10000, 'PokeWalk.bin', 'FoloToy-AI-Passport.bin')]
for _, source, target in IMAGES:
    dest = OUT / target
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BUILD / source, dest)
(OUT / 'flash_args').write_text('--flash_mode dio --flash_freq 80m --flash_size 8MB\n' +
    ''.join(f'{offset:#x} {target}\n' for offset, _, target in IMAGES))
merged = OUT / 'FoloToy-AI-Passport-full.bin'
subprocess.run([sys.executable, '-m', 'esptool', '--chip', 'esp32c3', 'merge_bin',
    '--flash_mode', 'dio', '--flash_freq', '80m', '--flash_size', '8MB', '-o', str(merged),
    *[arg for offset, _, target in IMAGES for arg in (hex(offset), str(OUT / target))]], check=True)
subprocess.run([sys.executable, str(ROOT / 'tools/release/verify_firmware.py'), str(OUT)], check=True)
report = {'artifact': merged.name, 'size': merged.stat().st_size,
          'sha256': hashlib.sha256(merged.read_bytes()).hexdigest(), 'flash_address': '0x0',
          'protected_layout_pass': True,
          'checker_source': 'FoloToy/ai-passport@df3990726e3751fadaaaa703a480dbba6e13c61b',
          'application_size': (BUILD / 'PokeWalk.bin').stat().st_size,
          'community_upload_performed': False, 'ble_install_tested': False}
(OUT / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
