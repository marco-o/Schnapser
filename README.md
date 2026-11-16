# Schnaps web site

A small site for playing Bauernschnapsen on the home network. Open it,
enter a nickname, and then:

- **start a table**, or **take a free seat** at someone else's (also during
  a running match), or **watch** any table;
- if you created the table, **fill seats** with the Neural player bot,
  remove bots, and **start the match** once all four seats are filled.

**How a match runs:**

- **Sets:** both pairs (South–North against West–East) start at **31** and
  count down by the points they win. The first pair at or below 0 wins the
  set.
- **Match:** best of **3 sets**. Then the creator can start a new match.
- **Dealer:** moves one seat clockwise after every deal. The **Caller**
  (chooses trump, bids first) is the dealer's left neighbour.
- **Deal points:**
  - Normal game: 1, 2 or 3.
  - Contracts: Schnapser 6, Lomt 9, Bauern 12, Jodler 18, Hermort 24.
  - Each fleck doubles the points.
  - A failed contract scores for the opponents.
- **Contracts end as soon as they are decided:**
  - **Schnapser:** the declarer's pair must win each of the first three
    tricks and reach 66 by then. The deal stops at the first trick the
    defenders win.
  - **Lomt and Bauern:** the deal stops at the first trick the declarer
    doesn't win.
- **20 and 40:** a declaration shows on the green table over the trick it
  leads ("Anna: 40 ♥ Herz"), and next to the player's name for the rest of
  the deal.
- **The Neural player bids with the set in mind.** It values a bid only by
  the points that still count for the set. It flecks only when the fleck
  can't cost the set (the other side needs no more points than the contract
  is worth, e.g. 9 or less against a Lomt), or when it's at least 75% sure.
- **Between deals:** the result shows for 5 seconds, then the next deal
  starts.
- **Disconnects:** the table waits for the player to come back. Reloading
  the page, or reopening it in the same browser, returns you to your seat.

Your seat is protected by a private token kept in your browser. Nobody,
including spectators, can see another player's cards.

## Running it

Everything runs in the WSL distro **Ubuntu**, from PowerShell.

1. **One-time setup:** Node 22 for the client build, plus FastAPI and
   uvicorn in the open_spiel venv.

   ```powershell
   wsl -d Ubuntu -- bash /mnt/c/Users/marco/Documents/git/Docker/schnaps-web/scripts/install.sh
   ```

2. **Build the client.** Repeat this after changing anything in `client/`.

   ```powershell
   wsl -d Ubuntu -- bash /mnt/c/Users/marco/Documents/git/Docker/schnaps-web/scripts/build_client.sh
   ```

3. **Start the site.** It takes about 30 s while the Neural player loads and
   compiles. Then open <http://localhost:8000>. Ctrl-C stops it.

   ```powershell
   wsl -d Ubuntu -- bash /mnt/c/Users/marco/Documents/git/Docker/schnaps-web/scripts/start_site.sh
   ```

The model is already in `models/neural_player`. To rebuild it from the
trained networks in `~` (`~/schnaps_normal@4000`,
`~/schnaps_forced_*@1000`), run `scripts/build_model.sh`.

Settings are environment variables `SCHNAPS_WEB_<NAME>`, for example
`SCHNAPS_WEB_BOT_DELAY=0.5` (seconds before each bot move),
`SCHNAPS_WEB_DEAL_PAUSE=5` or `SCHNAPS_WEB_PORT=8000`. The full list is in
`server/schnaps_web/config.py`.

## Playing from other devices on the LAN

The site runs inside WSL2, which sits behind its own network address, so
phones and other computers can't reach it directly. On Windows 10 you need
a port forward and a firewall rule. Both are Windows settings, so run them
yourself in an **Administrator** PowerShell:

```powershell
$ip = (wsl -d Ubuntu -- hostname -I).Trim().Split()[0]
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$ip
New-NetFirewallRule -DisplayName "Schnaps site" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

Other devices then open `http://<laptop IP>:8000`. `ipconfig` shows the
laptop's IP under the Wi-Fi adapter. WSL's address can change after a
restart; if the site stops answering from other devices, refresh the
forward:

```powershell
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
$ip = (wsl -d Ubuntu -- hostname -I).Trim().Split()[0]
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$ip
```

To undo both settings:

```powershell
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
Remove-NetFirewallRule -DisplayName "Schnaps site"
```

The site has no passwords; anyone on your network can open it. Keep the
firewall rule on the **Private** profile, so it applies only on your home
network.

## Tests

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/marco/Documents/git/Docker/schnaps-web/scripts/test.sh
```

They cover:

- scoring, sets, the match and dealer rotation (`tests/test_match.py`);
- whole deals and the privacy of each seat's view (`tests/test_deal.py`);
- the API and WebSocket: seats, permissions, privacy, a human move, and a
  complete match between bots (`tests/test_app.py`).

## Layout

```
server/schnaps_web/
  app.py        FastAPI: REST API, a WebSocket per table, serves client/dist
  lobby.py      the tables (in memory: they are gone when the server restarts)
  table.py      seats, tokens, the life cycle, the bot driver
  match.py      sets, matches, dealer and seat mapping (pure)
  deal.py       one deal on the pyspiel engine; each seat's view
  bots.py       the bot catalog (Neural player; Random for tests)
  config.py     settings
  game/         copied from the development tree (see below)
  tools/        build_player.py: assembles models/neural_player
client/src/
  lobby/        the lobby page
  table/        the table page: scoreboard, seats, result, score sheet
  net/          REST calls and the table's WebSocket
  gui/          the table UI, copied from the OpenSpiel GUI
models/neural_player/   the Neural player (four networks plus the bidder)
scripts/        install, build, start, test
```

## Card pictures

The card faces (William Tell pattern) are in
`client/public/cards/<rank><suit>.webp`, about 90 × 148 px each with
transparent corners. The rank is A, K, Q (Ober), J (Unter) or T (Zehn); the
suit is c (Kreuz), s (Pik), h (Herz) or d (Caro).

They were cut from `Docker/Pictures/schnapser-1.png` with
`scripts/cut_cards.py`. That sheet shows separate cards on a transparent
background: the rows are, top to bottom, Caro, Herz, Pik and Kreuz; the
columns are, left to right, Zehn, Unter, Ober, König and As. To recut them,
after `pip install pillow` in the venv:

```bash
scripts/run_py.sh ../scripts/cut_cards.py /path/to/schnapser-1.png ../client/public/cards \
  --transparent --rows dhsc --cols TJQKA
```

The script can also cut a photo of the cards on a table, finding,
straightening and trimming each card (its defaults fit the earlier
`Docker/Pictures/Schnapser.png`).

The table draws them through the schnaps skin's `faceImage`
(`client/src/gui/games/schnaps/schnaps_view.ts`). Face-down cards keep the
card library's back.

The suit signs (acorn, leaf, bell, heart) in `client/public/suits/<suit>.png`
replace the French suit glyphs: for the trump in the table's corner, on the
trump-choice buttons and in the 20/40 announcements. They were cut from
`Docker/Pictures/suits.png` (left to right: Kreuz, Pik, Caro, Herz) with:

```bash
scripts/run_py.sh ../scripts/cut_suits.py /path/to/suits.png ../client/public/suits
```

## What was copied from the development tree

The schnaps pieces built during development were **copied** here, so the
site doesn't depend on the development tree. They keep their Apache 2.0
licence headers.

| Here | From (`Docker/open_spiel/open_spiel/...`) |
|---|---|
| `server/schnaps_web/game/view.py` | `python/gui/adapters/schnaps_adapter.py` (as plain functions) |
| `server/schnaps_web/game/bidding.py` | `python/scale/envs/schnaps_bidding.py` |
| `server/schnaps_web/game/player.py` | `python/scale/envs/schnaps_player.py` (arch `schnaps_web.player`) |
| `server/schnaps_web/game/elena.py` | `python/scale/envs/schnaps_elena.py`, policy only (arch `schnaps_web.elena`, not offered yet) |
| `server/schnaps_web/tools/build_player.py` | `python/scale/examples/schnaps_build_player.py` |
| `client/src/gui/` | `gui/src/games/schnaps/`, `gui/src/cards/`, and the helpers they use. The renderer takes nicknames and draws your seat at the bottom |
| `models/neural_player/` | built from `~/schnaps_normal@4000` and `~/schnaps_forced_*@1000` |

Still used as installed libraries (not copied):

- the pyspiel game engine, `schnaps(max_flecks=2)`;
- the OpenSpiel scale framework, which loads and runs the networks.

Both come from `Docker/open_spiel` (its venv and `build/python`).

## Not done yet

- Elena as a selectable bot: one entry in `bots.py`.
- Saving tables across restarts.
- Docker packaging.
- Chat.
