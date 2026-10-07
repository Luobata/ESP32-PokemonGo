October 7: Move settings and warehouse management

Choose automatic battle moves for each individual partner from Party or Warehouse details > Moves. Learned moves start enabled; disable unwanted high-risk moves or enable all again. Keep at least one learned move enabled. Newly learned moves start enabled. Choices follow the individual through party changes, storage and evolution, and apply to wild, trainer and dungeon battles. During an active battle or dungeon, settings are read-only.

Release partners directly from the Warehouse without first moving them into the party. Confirmation shows name, level and a shiny warning, and defaults to Cancel. Only a successful save removes the individual; Pokédex and achievement history remain. Added ascending-level sorting to help locate lower-level partners. No bulk release.

Fixed save failures caused by superseded dungeon records taking up storage after multiple upgrades. Cleanup only follows full validation of retained progress or a successful new-record commit.

Save format is now V21. V5–V20 migrate with all moves enabled; V21 supports export/import round trips. Historical fixtures and isolated real NVS import/rollback tests passed. Hardware V20→V21 startup preserved progress, with repeated saves and a further restart verified. We did not overwrite-import the player's only hardware save. V21 cannot be restored into older firmware that does not support it.

Update firmware for these features. Back up first: https://luobata.github.io/ESP32-PokemonGo/
Existing devices with matching partitions can use PokeWalk-update.zip over USB. Full community installation overwrites the save area: back up, install, then restore. The current online/offline save protocol is unchanged. Refresh the website or download the offline ZIP for the new guide; early save tools should still be updated. Do not edit original .pksave files.

The Pikachu versus Gyarados cover and original video remain. Full guide: https://luobata.github.io/ESP32-PokemonGo/guide/
