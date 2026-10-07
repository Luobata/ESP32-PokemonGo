October 8: More reliable save imports

Fixed an import-validation path that allocated extra memory and reported allocation failures as incompatible save content or staging failure. Validation now reuses existing workspace while keeping save-content and safety checks intact.

Import errors now distinguish memory pressure, staging I/O, content validation, saving current progress and recovery-journal failures. An incomplete import is not reported as successful. Keep the original .pksave file without editing its version or checksums.

The save format remains V21, with V5–V21 sources supported. V5–V20 follow the existing migrations, with all moves enabled by default for older partners. Fixed historical fixtures and isolated real save import/rollback checks passed. New formats cannot be imported into older firmware that does not support them; unimplemented future formats are not guaranteed.

Update the device firmware for this fix. Refreshing the website alone cannot fix memory allocation in old firmware. Also refresh the online tool, or download a fresh offline ZIP, to see detailed errors. Existing backup files need no conversion.
Save manager: https://luobata.github.io/ESP32-PokemonGo/

Back up before updating. Existing devices with a matching partition layout can use PokeWalk-update.zip from GitHub Releases over USB to update only the application. Community full installation still overwrites the save area: back up first, then import after installation.

A community screenshot cannot identify every individual failure. If an error remains after updating, retain the complete error and original backup for diagnosis; do not upload private saves publicly.

Hardware validation passed: save-preserving update, cross-build import from the previous V21 release, and export/import on the new release, including the actual offline bundle. Pre-overwrite backup, confirmation, reboot and result correlation used production web logic with real serial hardware; native browser permission dialogs were not retested.
