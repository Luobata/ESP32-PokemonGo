October 4 fixes: Older save imports and Milk recovery

1. Fixed older backups being rejected after a game update solely because the firmware build changed. The same device can now import older save formats supported by the installed firmware (V5–V17 in this release). Original .pksave files need no conversion or editing.

2. The device checks the actual save content and version before replacing progress. Device confirmation, a backup of current progress, transfer integrity checks and power-interruption recovery remain in place. Other devices, damaged files and unsupported newer formats are still rejected.

3. Updated the online and offline web save tools to allow cross-version import. Update the device firmware and refresh the website, or download the offline ZIP again. Updating only one side may still show an incompatibility message. The developer command-line restore still requires the same build.

4. Moomoo Milk now restores half of maximum HP, rounded up, with a minimum of 50 HP and capped at full health, instead of a fixed 50. A partner with 300 maximum HP recovers 150; one with 500 recovers 250. It still clears status conditions and costs a turn in battle. Fainted partners, fully healthy partners without a status condition, and failed saves do not consume Milk. Its Care effect is unchanged.

Back up before updating; a full community installation may overwrite progress. Cross-version support does not allow newer saves to load on older firmware that cannot read their format.
Save manager: https://luobata.github.io/ESP32-PokemonGo/
