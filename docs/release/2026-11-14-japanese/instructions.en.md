Start and controls
Meet Professor Oak and choose Bulbasaur, Charmander, Squirtle or Pikachu. Existing saves resume offline. A selects the previous item, B the next and C confirms. Hold B to return; hold C to turn off the screen. After 60 idle seconds it turns off automatically. A press wakes without selecting. Home offers Care, Menu and Encounters. Battles choose learned, enabled moves automatically, without PP.

Language and shiny markers
Options > Language: press C for Simplified Chinese, Traditional Chinese, English or Japanese. The choice survives restarts and save restoration. Chinese name style stays separate. Shiny party members show a star.

Radar and map roaming
Menu > Radar scans nearby Wi-Fi without joining networks. A/B selects Track or Encounters; C confirms. Tracking costs five stamina and has a 120-second cooldown. The environment selects the pool; without signals you cannot track. Dots are not GPS, distance or direction.
After starting Johto, Menu > Roam opens the park at two Johto badges, ruins at three and Burned Tower at four. A/B selects a destination, C walks there, then C interacts. Read the sign or NPC and observe two other traces to reach 3/3. Search at the fourth destination. Walking and observation are free; successful searches cost five stamina and reset the three observations, with a separate 180-second cooldown per map.
Successful map searches advance route research and carried-egg exploration; observation alone does not advance hatching or legendary evidence. Cooldowns use powered-on time and survive reopening/restarting. A full five-encounter list blocks new searches without replacing partners or charging stamina.

Shiny partners and exploration chains
Radar odds start at 1/32 (3.125%); roaming at 1/24 (about 4.17%), independent of species rarity. Species remain rarity-weighted. For w exploration wins and base denominator d, odds are approximately 1/d + (1−1/d)×w/(w+2304). Discovery adds no win. Exploration victories grow the chain; confirming capture or losing an exploration battle ends it. Capture has a second confirmation. Leaving, changing maps and restarting retain the chain; generated partners are not rerolled.

Care, exploration and growth
Feed uses berries even at low stamina; Play needs five stamina. Care improves experience, discoveries and capture timing. Stamina caps at 100 and refills in about an hour. Ordinary exploration and route trainer practice cost five; Gym/rematch/Red battles ten; an Elite Four/Champion run twenty. Routes have different pools and local level limits. During capture, A/B changes balls and C throws in the blue window. Failure allows a counterattack; choosing Battle commits to the fight. For eligible evolutions, put the partner first and confirm in Care > Evolve.

Johto and activities
With four Kanto badges, open Menu > Johto.  Read the invitation, choose a starter and follow the Adventure Journal. C advances dialogue, A/B chooses, hold B pauses for later. No replay rewards. Legendary fieldwork asks for a branch and suitable living party member. Correct actions cost five stamina; hints and wrong choices are free. Solutions are collapsed in the guide.
The first Johto badge grants Togepi's egg; carry it through 12 valid Johto explorations, then hatch. At two badges, bring one partner and pay ten stamina for a six-point bug survey. You have THREE throws for the whole run, using your own balls. Select Throw, then press C while the pointer is blue. Without throws or balls, throwing is disabled. Compare catches and keep one. Completing six observations grants story evidence even without a catch. Goldenrod research at six and twelve visits unlocks starter rescues.
Unown walls open at three badges. Ice, whirl and tower expeditions open at five, six and seven: bring three partners, pay twenty stamina. HP/status persist; relays let you bank rewards or continue. Whirl depths grant the Silver Wing. The five-badge Lake of Rage story awards a guaranteed shiny red Gyarados; cancelled/full-storage claims remain available. After Red, Johto Gyms gain champion teams and separate achievements. The Journal guides Elm's final trial.

Party, storage and moves
Six party slots and 753 warehouse slots preserve individuals, including duplicates. In party/warehouse details, open Moves: A/B selects, C toggles, hold B returns. Keep at least one enabled move; new moves start enabled. Settings follow the individual and are read-only during battles/expeditions.
Release directly from warehouse details; confirmation defaults to Cancel and shows name, level and shininess. Release is irreversible; save failure keeps the partner. Hold A in storage for filters/sorting. Release is unavailable during battles/expeditions.
At full storage, a capture asks you to select a warehouse replacement and confirm again; hold A changes sorting. Holding B can abandon the new capture after confirmation. No automatic replacement occurs. Keep power on until stored.

Sound, display and Wi-Fi
New installs start with sound at 55%; saved mute/volume choices remain. Options > Mute toggles sound; raising volume does not unmute. Brightness opens a gauge: A +10%, B −10%, C finishes, hold B returns. Range 10–100%, saved immediately across wake/reboot. Battery appears near names in Menu/Care; low is red.
Open Options > Wi-Fi Time and press C. Join the PW- hotspot using the device's displayed password. Keep connected despite “no internet”, then open the full http://192.168.4.1 (not https). This is the device's local page, not a public website. Enter an available 2.4 GHz network or another device's hotspot credentials, then Connect and Save. The page acknowledges first; the hotspot then closes to connect. Confirm Time Synchronized on the device. Only successful connections save credentials.
Setup pauses background scanning, accepts two clients and shows their count. Missing-network, authentication, connection and startup failures have separate messages. If the page will not open, temporarily disable automatic cellular switching/VPN or forget the old PW- network and rejoin. Setup lasts five minutes; C closes it, hold B returns, A outside setup retries. Saved networks reconnect at boot. First sync sets a time reference; later boot sync restores powered-off stamina. Offline play still works.

Backup, restore and updates
Desktop Chrome/Edge: https://luobata.github.io/ESP32-PokemonGo/. Choose a private folder, connect USB, authorize the serial port and close other serial tools. On the device open Menu > Options > Back Up Save and press C. Wait for file write/readback and completion. Saves stay on your computer.
To restore, open Options > Import Save, choose a .pksave on the website and request import. On the device change Cancel to overwrite and confirm. Current progress is backed up first. After restart, reconnect and verify the receipt, partners, levels and Pokédex. Same-device V5–V32 backups migrate automatically; newer saves cannot go into unsupported older firmware. Developer restore.py cannot restore expanded storage; use the website.
Update firmware for these features; save format and partitions are unchanged. Refresh the guide for new instructions; format-4 offline tools remain compatible. Back up before updating. A full community installation may erase progress, requiring restoration afterwards. Existing devices should prefer PokeWalk-update.zip from https://github.com/Luobata/ESP32-PokemonGo/releases/latest over USB; follow its README. It validates layout and backs up before writing. If export fails, keep existing backups and use the protected update instead of full installation over your only progress.
Offline tool: unzip the download, run python3 server.py (Windows: py -3 server.py) with Python 3.8+, open http://localhost:8767/. Keep backups and errors on failure.
Guide: https://luobata.github.io/ESP32-PokemonGo/guide/

For resilient imports, refresh the website or download the new offline tool.
