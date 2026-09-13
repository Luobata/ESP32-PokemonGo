# Community packaging

Run `python tools/release/package_firmware.py` inside the ESP-IDF Python environment after a firmware build. Output is local, ignored `release/community/`. This does not flash a device or upload anything.

`verify_firmware.py` is the unmodified upstream checker from [FoloToy/ai-passport, df399072](https://github.com/FoloToy/ai-passport/blob/df3990726e3751fadaaaa703a480dbba6e13c61b/tools/verify_firmware.py), retrieved 2026-09-09. Its MIT license is retained in `LICENSE.upstream`. This license applies to that upstream checker, not to game artwork or music.

The merged image contains bootloader, partition table and app only. It contains no player's NVS, card identity or permanent Recovery payload. A full image has blank padding over NVS: for an existing player device, back up first and update only the intended components while retaining NVS. This USB import release adds a staging partition, so its first upgrade requires both the partition table and application; application-only flashing keeps backup but cannot enable import.
