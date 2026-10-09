This release fixes saving failures caused by insufficient shared storage on some devices. Update the firmware; refreshing the website alone cannot fix it. Same-device V5–V22 backups are supported, with automatic migration and no manual file editing. V22 cannot be imported into older firmware that does not support it. The current online and offline backup protocol is unchanged.

Keep your original .pksave. If the older firmware cannot export, use PokeWalk-update.zip over USB on a device with a matching partition layout. It backs up and verifies the data partitions and writes only the app. Do not overwrite your only save with a full installation. Community full installation may erase saves; import your backup afterwards.

Start your adventure
Follow Professor Oak and choose Bulbasaur, Charmander, Squirtle or Pikachu. Existing saves resume automatically. The game works offline without Wi-Fi setup.

Controls
A moves up, B down, C confirms. Hold B to return; hold C to sleep. Idle sleep starts after about 60 seconds. Any function key wakes the screen; the wake press does not activate a menu. For capture, A/B change balls and C throws when the moving marker is inside the blue window. Follow on-screen prompts.

First steps
From Home choose Care, Menu or Encounters. Menu contains Pokédex, Party, Items, Care, Challenges, Options, Achievements, Exploration and Dungeon. Begin with Exploration, select a route and find a partner, then capture or battle. Battles choose learned moves automatically, without PP. When a partner meets evolution requirements, put it first and select Care > Evolution.

Care, stamina and playtime
Feed a berry for satiety; playing costs 5 stamina and is unavailable below that amount. Feeding remains available. Care Benefits explains XP, special-event and capture-window bonuses. Shared stamina caps at 100 and refills in about an hour. Exploration and route trainers cost 5, Gym/rematch/Red challenges cost 10, and an Elite Four plus Champion run costs 20 once. New dungeon runs cost 20; continuing costs no additional entry fee. Menu and Care show cumulative screen-on playtime across restarts. Older unrecorded time cannot be reconstructed.

Regions and dungeons
Rainbow Badge opens Twin Islands and Safari Fields; Soul opens Ghost Tower; Marsh opens Magnetic Mine; Volcano opens Volcanic Ruins; Earth opens Dragon Valley. Defeating the Champion opens Abandoned Lab, then one completed regional study opens Silver Snow Ridge. Eight completed studies unlock Champion Expedition.
Choose Exploration in a new region, then a habitat trail; only confirming spends 5 stamina. Regional level bands are Twin Islands 35–45, Ghost Tower 42–55, Safari Fields 38–50, Magnetic Mine 45–58, Volcanic Ruins 48–60, Dragon Valley 50–65, Abandoned Lab 60–75 and Silver Snow Ridge 65–85. Deep exploration uses the upper half after five local species are discovered. Original routes still scale to your partner. Existing encounters do not reroll when you switch partners or restart.
Trails show two visitors, rotating every 12 explorations of that region. Regional clues are shared, so tracked/guaranteed encounters may use another trail. Regional studies require five discoveries, three captures, a completed tracking target and the local dungeon clear. Claim their one-time rewards in Activities.
Enter local dungeons through Activities or choose a theme in the Dungeon lobby. Select 1–3 of your own partners. HP and status persist between nodes; choose upgrades, rest at camps and defeat the boss. Local first clears unlock a harder mode. After a new-theme clear, select a direction to find a rare capturable partner, then capture it from Encounters. If a new-theme reward cannot fit, collect it later in the lobby or discard after confirmation before starting another run. The original Forest reward enters the five-slot encounter list, replacing its oldest entry if full. Settled rewards remain after defeat or retirement.

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
To restore, open Options > Import Save, select a .pksave in the website and request import. The device defaults to Cancel; explicitly select overwrite and confirm. Your current save is backed up first, then import and restart proceed. Reconnect and verify the result and your progress. V5–V21 migrate to V22; V22 can round-trip. V5–V20 default to all learned moves enabled, while existing V21 move settings are preserved. Same-device identity and a matching layout are still required. Different build hashes alone do not block import. Do not edit backups or import V22 into older unsupported firmware. The developer restore.py command still requires the same build; use the website for cross-version restore.
Back up before updating. Full community installation overwrites the old save area, so import afterwards. Existing devices with matching layouts can use PokeWalk-update.zip from https://github.com/Luobata/ESP32-PokemonGo/releases/latest over USB, following its README. Do not submit the update ZIP as a community installation image.
This fix needs new firmware. Current online and offline backup protocols are unchanged; older tools predating the cross-build fixes should be refreshed or downloaded again. A website refresh alone cannot fix old firmware. Offline: run python3 server.py (Windows: py -3 server.py) with Python 3.8+ and open http://localhost:8767/. Keep original backups and full error messages if import fails.

Complete game guide: https://luobata.github.io/ESP32-PokemonGo/guide/

Names and shiny entrances
Press C on Menu > Options > Names to switch Official/Nostalgic. The historical Chinese species names now also select matching move names; only displayed names change. Shiny Pokémon play a sparkle when actually sent out; mute suppresses the sound.
