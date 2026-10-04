October 5: Legacy saves and verified import results

1. Hardened older-save migration, fixing reserved bytes in some early formats being mistaken for invalid data. This release supports V5–V17 on the same device. Keep your original .pksave; no editing is needed.

2. Fixed the web tool accepting an old restore receipt as success for the current import. Completion now requires the selected file to match the device result after restart. A game startup load failure is reported separately.

3. Added a save-preserving USB update package for existing PokeWalk devices with a matching layout. It backs up data before updating and verifies that save regions are unchanged afterwards. Download and instructions: https://github.com/Luobata/ESP32-PokemonGo/releases/latest

4. Added 17 historical save fixtures covering migration, startup, saving and importing again, and retained settings. Future format changes must include migration and historical regression checks.

Before updating: back up, then update the device firmware. Refresh the online tool or download an old offline tool again. Refreshing the website alone cannot apply the new firmware migration fixes. A full community installation overwrites the old save area: back up first and import afterwards. The USB update package is not a community installation image.

Save manager: https://luobata.github.io/ESP32-PokemonGo/
Keep the original backup. Unsupported newer formats, damaged files and other devices are still rejected. New formats are not supported on older firmware automatically; future compatibility must be verified release by release.
