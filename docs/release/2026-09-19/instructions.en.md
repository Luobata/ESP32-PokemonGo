Start your adventure
On first boot, follow Professor Oak's introduction and choose Bulbasaur, Charmander, Squirtle or Pikachu. An existing save resumes your progress. You can play offline without setting up Wi-Fi.

Controls
A moves up, B moves down and C confirms. Hold B to return; hold C to turn the screen off. It also sleeps after about 60 idle seconds. Any function button wakes it, consuming that first press. During capture, A/B change balls and C throws; follow each screen's prompts.

Your first steps
Select Care, Menu or Encounters on the home screen with A/B, then C. The menu includes Pokédex, Party, Items, Care, Challenges, Options, Achievements, Exploration and Dungeon. Start in Exploration, choose a route and find a partner, then choose capture or battle. Battles select learned moves automatically without PP management. Playing requires at least 5 stamina; you can still feed a berry when stamina is low. When a partner meets its evolution requirement, make it the leader and confirm in Care > Evolution.

Stamina and challenges
Stamina caps at 100 and recovers from empty in about one hour. Exploration and route-trainer matches cost 5, Gym/rematch/Red challenges cost 10, and an Elite Four plus Champion run costs 20 once. Choose 1–3 of your own partners for the Forest dungeon. A new run costs 20, continuing costs no extra entry fee. Dungeon HP and status persist between nodes; rewards already settled remain after defeat or retirement.

Sound and brightness
Options has mute, volume and brightness. Press C to edit volume or brightness, A to increase, B to decrease and C to finish. Brightness ranges from 10% to 100%. Preferences survive restart. Adjusting volume does not disable mute.

Wi-Fi Time and powered-off stamina
Open Menu > Options > Wi-Fi Time and press C to start setup. Connect your phone to the temporary PW- hotspot shown on the device, using its displayed password. Stay connected even if the phone says there is no internet. Open http://192.168.4.1 in the browser, enter a working 2.4 GHz home Wi-Fi network or another device's hotspot name and password, then submit. Check the game screen: “时间已同步” means time is synchronized.
The setup hotspot closes after about five minutes. C closes or reopens it; holding B returns and closes setup. If connection fails, check the network details and open setup again. Outside setup, A retries connection/time sync. A successful network is saved for later boots. The first time sync establishes a baseline; later startup syncs restore powered-off stamina. Offline play remains available.

Backup and import
Open https://luobata.github.io/ESP32-PokemonGo/ in desktop Chrome/Edge. Select a private folder, connect the device using a USB data cable and authorize its serial connection. Close other serial monitors. On the device, open Options > Backup and press C. Wait until the website saves the file and the device confirms completion. Saves stay on your computer.
For import, first open Options > Import on the device, select a .pksave file on the website and request import. Cancel is selected by default on the device; choose confirmation and press C to proceed. Current progress is backed up before importing, then the device restarts. Reconnect to verify the result. Import requires the same device and exact firmware build. Keep the installer that matches your backup.
For offline use, download and extract the tool ZIP from the site. With Python 3.8 or later, run python3 server.py (or py -3 server.py on Windows) and open http://localhost:8767/. Download the tool again for this fix. Future games using the same backup format and layout do not need another tool update.

Back up before updating. A full community installation may overwrite saves. Backup support does not imply arbitrary cross-firmware restore support.
