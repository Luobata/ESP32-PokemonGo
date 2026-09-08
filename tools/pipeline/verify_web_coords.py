#!/usr/bin/env python3
"""Compatibility entry for the former JS/firmware coordinate-copy gate.

P0-P6 now execute the production C pages and deliver their LCD bytes to Canvas.
The old JS simulator is explicitly a design/reference surface, so comparing its
copied coordinates would no longer check the authoritative preview. Retire that
migration table in favor of the actual seven-page rendering/dirty-band/decoder
gate, including mutations that prove it detects missing redraws and DMA waits.

This checks rendering parity, not the visual quality of page layouts. Layout,
GSC tile fidelity and browser Canvas readback have separate checks/evidence.
"""
from verify_firmware_preview import main


if __name__ == "__main__":
    raise SystemExit(main())
