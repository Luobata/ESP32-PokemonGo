# Upstream power lifecycle changes

The 2026-09-15 power update adapts audio/display initialization rollback from
[FoloToy/ai-passport](https://github.com/FoloToy/ai-passport/tree/cd73a8a6f1f95e010bfd83a08e2b915e38408308).
`src/bsp_es8311_sleep_check.c` and `.h` are copied unchanged from that revision,
including the REG0E valid-bit mask from commit `12f684d`.
The upstream MIT license is retained in `LICENSE.upstream`.

PokeWalk keeps its own boot mute, single sound worker, screen wake behavior,
background encounter alerts and data partitions. It does not import the demo's
MCU deep sleep or irreversible bus/pin shutdown APIs.
