The warehouse now holds 453 individual partners, in addition to your party of six. You can catch the same species more than once. Saves V5–V23 from the same device are supported; V5–V22 migrate automatically without editing your .pksave. New saves cannot be imported into older unsupported firmware.

Update the game and refresh the online save manager or download the offline tool again. The new PokeWalk-update.zip checks the existing layout, adds only the warehouse storage area on the first upgrade, backs up and verifies your data, and restarts only after verification. Existing storage locations stay unchanged. Community full installation may erase progress: back up first and import afterward. If the old game cannot export, keep existing backups and use the new USB update package, not a full installation over your only save.

Capturing with a full warehouse
After a successful catch, use A/B to select a warehouse partner and C to open the second confirmation. Hold A to switch between level and species sorting. Cancel is selected by default; the screen shows both partners, levels and shiny warnings. Hold B to choose to release the new catch, also with confirmation. Keep the device on until your choice is saved; the new catch is not persistent before that. Existing partners are never automatically replaced.

Start your adventure
Follow Professor Oak and choose Bulbasaur, Charmander, Squirtle or Pikachu. Existing saves resume automatically. The game works offline without Wi-Fi setup.

Controls
A moves up, B down, C confirms. Hold B to return; hold C to sleep. Idle sleep starts after about 60 seconds. Any function key wakes the screen; the wake press does not activate a menu. For capture, A/B change balls and C throws when the moving marker is inside the blue window. Follow on-screen prompts.

First steps
From Home choose Care, Menu or Encounters. Menu contains Pokédex, Party, Items, Care, Challenges, Options, Achievements, Exploration and Dungeon. Begin with Exploration, select a route and find a partner, then capture or battle. Battles choose learned moves automatically, without PP. When a partner meets evolution requirements, put it first and select Care > Evolution.

Care, stamina and playtime
Feed a berry for satiety; playing costs 5 stamina and is unavailable below that amount. Feeding remains available. Care Benefits explains XP, special-event and capture-window bonuses. Shared stamina caps at 100 and refills in about an hour. Exploration and route trainers cost 5, Gym/rematch/Red challenges cost 10, and an Elite Four plus Champion run costs 20 once. New dungeon runs cost 20; continuing costs no additional entry fee. Menu and Care show cumulative screen-on playtime across restarts. Older unrecorded time cannot be reconstructed.

Regions and dungeons
Badges open eight new regions with their own level ranges and three habitat trails each. Existing encounters keep their generated level. Exploration costs 5 stamina only after confirming a direction; deep exploration opens after discovering five local species and uses the upper part of the region’s level range. Research requires discovery, capture, tracking and the local dungeon; check Activities for requirements and rewards.
Enter a dungeon from Activities or choose a theme at the dungeon entrance. Select up to three of your own partners; a new run costs 20 stamina, continuing costs no extra entry fee. HP and status carry between nodes, while settled rewards stay even after defeat or leaving. First clears unlock challenge difficulty. Clear rewards can include a capturable partner: choose a habitat and return to Encounters to catch it. Pending themed rewards wait at the entrance when there is no space. Full route, unlock and reward tables are in the linked guide.

Exploration chains
Wild wins from map exploration or badge activities build a shiny chain for future encounters. Changing pages/regions, restarting or playing other battle modes preserves it. Losing an exploration battle or confirming capture resets it. With a chain, capture opens a second confirmation defaulting to Cancel; use A/B and C. Cancelling spends no ball and preserves the chain. Escaping does not add or reset it.

Items and achievements
Claims are allowed when stacks are full; rewards fill remaining capacity and excess is not added. Higher-rarity wild opponents drop better balls and evolution items more often. Trainer matches and exploration clues provide food. In trainer/Gym/league battles, Tactics > Milk heals at least 50 HP or half maximum HP (rounded up), whichever is higher, capped at full HP, and clears status. It uses one turn and cannot revive a fainted partner.

Options
Toggle mute and battery display, or press C to adjust volume/brightness with A/B and finish with C. Brightness ranges from 10% to 100%. Raising volume does not unmute. Battery appears beside the partner name in Menu and Care. Settings persist after restart.

Wi-Fi time and offline stamina
Open Options > Wi-Fi Time and press C to start setup. Connect a phone to the PW- hotspot and password shown on the device, staying connected despite the no-internet warning. Open http://192.168.4.1 and enter an available 2.4 GHz Wi-Fi network or a second device's hotspot, then select Connect and Save. The device shows Time Synchronized on success. Setup closes after about five minutes; C toggles it and holding B leaves it. Retry with corrected details if needed; outside setup, A retries time sync. Successful credentials are stored for the next boot. Initial sync establishes the time reference, and a later boot sync credits time spent powered off. Offline play remains available.

Backup, update and restore
Use desktop Chrome/Edge at https://luobata.github.io/ESP32-PokemonGo/, choose a private backup folder, connect USB and authorize the serial port. Close competing serial tools. On the device select Options > Back Up Save and C. Wait for the website to save and read back the file and the device to confirm. Files stay on your computer.
To restore, open Options > Import Save, select a .pksave in the website and request import. The device defaults to Cancel; explicitly select overwrite and confirm. Your current save is backed up first, then import and restart proceed. Reconnect and verify the result and your progress. V5–V22 migrate to V23; V23 can round-trip. V5–V20 default to all learned moves enabled, while existing V21 move settings are preserved. Same-device identity and a matching layout are still required. Different build hashes alone do not block import. Do not edit backups or import V23 into older unsupported firmware. The developer restore.py retains its same-build protection and does not directly restore expanded warehouses; use the website.
Back up before updating. Full community installation overwrites the old save area, so import afterwards. Existing devices with matching layouts can use PokeWalk-update.zip from https://github.com/Luobata/ESP32-PokemonGo/releases/latest over USB, following its README. Do not submit the update ZIP as a community installation image.
This fix needs new firmware. New backups include the expanded warehouse. Refresh the online tool or download the offline tool again before exporting or importing V23 backups. A website refresh alone cannot fix old firmware. Offline: run python3 server.py (Windows: py -3 server.py) with Python 3.8+ and open http://localhost:8767/. Keep original backups and full error messages if import fails.

Complete game guide: https://luobata.github.io/ESP32-PokemonGo/guide/

Names and shiny entrances
Press C on Menu > Options > Names to switch Official/Nostalgic. The historical Chinese species names now also select matching move names; only displayed names change. Shiny Pokémon play a sparkle when actually sent out; mute suppresses the sound.
