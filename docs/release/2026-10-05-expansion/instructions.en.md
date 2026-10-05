Start your adventure
On first boot, follow Professor Oak's introduction and choose Bulbasaur, Charmander, Squirtle or Pikachu. An existing save resumes your progress. You can play offline without setting up Wi-Fi.

Controls
A moves up, B moves down and C confirms. Hold B to return; hold C to turn the screen off. It also sleeps after about 60 idle seconds. Any function button wakes it, consuming that first press. During capture, A/B change balls and C throws; follow each screen's prompts.

Your first steps
Select Care, Menu or Encounters on the home screen with A/B, then C. The menu includes Pokédex, Party, Items, Care, Challenges, Options, Achievements, Exploration and Dungeon. Start in Exploration, choose a route and find a partner, then choose capture or battle. Battles select learned moves automatically without PP management. Playing requires at least 5 stamina; you can still feed a berry when stamina is low. When a partner meets its evolution requirement, make it the leader and confirm in Care > Evolution.

Stamina and challenges
Stamina caps at 100 and recovers from empty in about one hour. Exploration and route-trainer matches cost 5, Gym/rematch/Red challenges cost 10, and an Elite Four plus Champion run costs 20 once. Choose 1–3 of your own partners for the Forest dungeon. A new run costs 20, continuing costs no extra entry fee. Dungeon HP and status persist between nodes; rewards already settled remain after defeat or retirement.

Battery display
Menu and Care show battery level beside your partner’s name; 20% or less is red. Toggle it with C in Menu > Options > Battery Display. Your choice survives restart.

Achievements and dungeon partners
Full item stacks no longer block achievement claims. Rewards fill only to their holding limit; excess is not added. Clearing and settling the final Forest dungeon boss adds one capturable partner to Encounters. Select it there and throw a ball normally. At the five-encounter limit, the oldest is replaced.

Sound and brightness
Options has mute, volume and brightness. Press C to edit volume or brightness, A to increase, B to decrease and C to finish. Brightness ranges from 10% to 100%. Preferences survive restart. Adjusting volume does not disable mute.

Wi-Fi Time and powered-off stamina
Open Menu > Options > Wi-Fi Time and press C to start setup. Connect your phone to the temporary PW- hotspot shown on the device, using its displayed password. Stay connected even if the phone says there is no internet. Open http://192.168.4.1 in the browser, enter a working 2.4 GHz home Wi-Fi network or another device's hotspot name and password, then submit. Check the game screen: “时间已同步” means time is synchronized.
The setup hotspot closes after about five minutes. C closes or reopens it; holding B returns and closes setup. If connection fails, check the network details and open setup again. Outside setup, A retries connection/time sync. A successful network is saved for later boots. The first time sync establishes a baseline; later startup syncs restore powered-off stamina. Offline play remains available.

Backup and import
Open https://luobata.github.io/ESP32-PokemonGo/ in desktop Chrome/Edge. Select a private folder, connect the device using a USB data cable and authorize its serial connection. Close other serial monitors. On the device, open Options > Backup and press C. Wait until the website saves the file and the device confirms completion. Saves stay on your computer.
For import, first open Options > Import on the device, select a .pksave file on the website and request import. Cancel is selected by default on the device; choose confirmation and press C to proceed. Current progress is backed up before importing, then the device restarts. Reconnect to verify the result. Import requires the same device and a save format supported by the installed firmware. This release reads older V5–V18 saves without requiring an identical firmware build. Newer unsupported saves cannot be imported into older firmware. Keep your original .pksave file; no conversion or editing is needed.
For offline use, download and extract the tool ZIP from the site. With Python 3.8 or later, run python3 server.py (or py -3 server.py on Windows) and open http://localhost:8767/. For cross-version import, update the device firmware and refresh the website, or download the offline ZIP again. Updating only the website cannot remove an old firmware restriction. The developer restore.py command still requires an identical build; use the online or offline web tool for cross-version import.

Milk recovery
In trainer, Gym and League battles, Tactics > Milk Recovery restores half of maximum HP, rounded up, with a minimum of 50 HP and capped at full health. It also clears status conditions and costs one turn. Fainted partners cannot use it. Its Care effect remains +20 fullness and +10 mood.

Update and restore
Save a .pksave before updating. Full community installation overwrites the previous save area; import your backup after installation. Existing PokeWalk devices with a matching layout can instead download PokeWalk-update.zip from https://github.com/Luobata/ESP32-PokemonGo/releases/latest and follow its README for a USB update with a pre-update backup. Do not upload this ZIP as a community installation image.
The web tool confirms completion only when the current file matches the result after restart. If it is waiting or reports an error, retain the original backup and check your device. New regions and V18 migration require new firmware; refreshing the website does not add game content.

New regions and themed dungeons
Exploration > Routes lists unlocked regions only. The Rainbow Badge opens Twin Islands and Safari Fields; Soul opens Ghost Tower; Marsh opens Magnetic Mine; Volcano opens Volcanic Ruins; Earth opens Dragon Valley. Defeat the Champion to open Abandoned Lab, then finish one new regional research to open Silver Snow Ridge. Complete all eight regional research records to unlock Champion Expedition.
Choose Explore and one of three directions for 5 stamina. Discover five local species to enable deeper investigation in Activities, also for 5 stamina. Research requires five discoveries, three captures, one completed tracking target and a local dungeon clear; existing Pokédex records count. Check and claim the one-time research reward in Activities.
Enter the local dungeon from Activities, or use Dungeon > Theme. Select 1–3 owned partners for a new run costing 20 stamina; continuing costs no extra entry fee. A local first clear unlocks challenge difficulty. After a clear, choose a partner direction, then catch the partner in Encounters. New themes hold rewards when encounters or item stacks are full instead of replacing old encounters. Collect pending rewards in the lobby, or discard after a second confirmation, before starting another run. Original Forest reward rules remain.
This release uses V18 saves and migrates older dungeon progress. Current online tools and the offline tools fixed on October 5 already handle the format. Older tools still require a refresh or new download. Never edit backup contents.

Trails and levels
The 24 new habitat trails have different partner pools. Choices show example partners and normal/deep level bands. Regional clues are shared; tracked or guaranteed encounters may use another trail. Normal bands: Twin Islands 35–45, Ghost Tower 42–55, Safari Fields 38–50, Magnetic Mine 45–58, Volcanic Ruins 48–60, Dragon Valley 50–65, Abandoned Lab 60–75, Silver Snow Ridge 65–85. Deep exploration uses the upper half. New-region levels no longer follow your leader; switching partners or restarting cannot reroll them. Original routes still scale to your partner and existing encounters retain their levels. Only confirming a trail costs 5 stamina; moving the cursor or cancelling is free.
