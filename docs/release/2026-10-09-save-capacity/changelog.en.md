2026.10.09 · Save storage capacity fix

Fixes saving failures on some updated devices that could also block backup or import checkpoints. The supplied player backup reproduced insufficient shared NVS capacity in an isolated environment. The backup is valid; no manual version changes are required.

Lossless save storage preserves partners, levels, experience, shinies, warehouse, move settings, Pokédex, items, care and challenge progress. Same-device V5–V22 backups are supported through automatic migration. Older firmware cannot accept V22 unless it supports that format.

Update the firmware; refreshing the website alone is insufficient. The online/offline backup protocol is unchanged. Back up first. PokeWalk-update.zip updates only the app over USB on a matching partition layout; community full installation may erase saves and requires restoring the backup afterwards. If the old firmware cannot export, preserve existing backups and use the save-preserving update package instead of overwriting the only save.

Historical migration, full storage, repeated writes, garbage collection, export/import and interrupted writes were checked. See the repository release record for physical-device results and artifact hashes. Reports without the original error logs still require stage-specific diagnosis; this is not a guarantee against every storage failure.
