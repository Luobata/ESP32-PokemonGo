2026.10.26 · Bug Survey Capture and Smoothness Fixes

Responsive throws and visible-position judgment
With Throw selected, pressing C starts the throw without waiting for release. The result uses the pointer position last shown on screen. One gesture makes one attempt; releasing the button after a save failure cannot silently retry or spend another ball.

One capture strip across both modes
Bug surveys now share the ordinary capture frame, arrow and blue-window renderer. Changing the target or ball, or returning to the page, rebuilds the current display and clears the outside of a narrower window. The visible target is locked with the throw and checked again before settlement.

Smoother capture presentation
Pointer updates redraw only the strip; throw animations redraw only their changing area. Hardware pointer samples measured about 24.8 frames per second. The 1.2-second pointer cycle, capture formula, ball bonuses and motion timings are unchanged. Saving occurs at the still open-ball pose after flight starts; absorption, bounces and shakes resume without skipping motion.

Clear run-wide throw allowance
The label now shows balls remaining for this run. There are THREE attempts across the entire six-point survey, not three per candidate. With no attempts or no stock of the selected ball, the page no longer shows an active capture strip or starts a fake throw. You can still change balls, observe further or settle early. All six observations grant the story record without requiring a catch.

Updating and validation limits
Update firmware for these fixes; refreshing the website alone does not fix the device. Saves remain V32 with same-device V5–V32 support and unchanged partitions/container. Do not edit old backups. The backup protocol is unchanged; refresh the website for revised instructions, while existing format-4 offline tools remain usable.
Back up first. Existing installations should prefer the USB save-preserving update ZIP. Full community installation may erase progress, so back up and restore afterwards.
Continuous target checks covered all 15 survey species. Hardware tests covered successful Yanma capture and failed retries. The reported oversized first window was not reproduced, so this is not a claim that every similar symptom is resolved. One hardware import timed out safely before overwrite; retry and actual progress comparison succeeded. This is not presented as a new fix for all save failures.

Guide: https://luobata.github.io/ESP32-PokemonGo/guide/#johto
Downloads: https://github.com/Luobata/ESP32-PokemonGo/releases
Community availability follows review approval.
