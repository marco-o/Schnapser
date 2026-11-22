# Schnaps web site

A small site for playing Bauernschnapsen on the home network. Open it,
say who you are (an account, or a guest nickname), and then:

- **start a table**, or **take a free seat** at someone else's (also during
  a running match), or **watch** any table;
- if you created the table, **fill seats** with the Bologna, Firenze or Verona bot,
  remove bots, and **start the match** once all four seats are filled;
- see the **ratings** of every pair in the lobby.

**Accounts and ratings:**

- **Register** in the lobby with a username and a password (**Log in or
  register**). The device then remembers the account: next time the lobby
  only asks **Who's playing?** with one button per account on that device
  (no password). A shared tablet can remember several accounts; **Log out**
  forgets one on that device.
- **Guests** still play with just a nickname, unrated. A guest can't use a
  registered username.
- **Pairs are rated, not players** (Elo). A pair is two players, whatever
  their seats; bots count by their kind ("Anna & Bologna bot", "Verona bot
  & Verona bot"), never by the first names they get at a table, so all
  Verona + Verona pairs are one pair. Every pair starts at **600**.
- **Each set changes the ratings.** The winners gain and the losers drop
  32 × (1 − E), where E = 1 / (1 + 10^((loser − winner) / 400)) is the
  winners' expected score: 16 points between equal pairs, more for an
  upset.
- **A set counts only if** every seat had the same logged-in user or bot
  for the whole set, and the two pairs differ (Verona + Verona against
  Verona + Verona doesn't count). Tables with only bots count too.
- **Where you see it:** the lobby's **Ratings** list (best first, won–lost
  sets, "Only my pairs"), each table's pair ratings in the lobby and on the
  scoreboard, and the change ("600 → 616 (+16)") or why a set wasn't rated
  in the result when a set ends.
- **The database** is three small files in `data/db/` (not in git):
  `users.json` (usernames, salted PBKDF2 password hashes, hashes of the
  device keys), `ratings.json` (each pair's rating and won–lost), and
  `sets.jsonl`, one line per finished set: the table, the match, the four
  players, every deal of the set, the winner and the rating change. The
  ratings can be rebuilt from that log (`Db.rebuild_ratings` in
  `server/schnaps_web/db.py`).

**How a match runs:**

- **Seats:** seats 1 and 3 are partners, so are seats 2 and 4. Players and
  pairs are shown by name only (no compass points).
- **Sets:** both pairs start at **31** and
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
- **On the green table, next to each name:** the trump's suit sign next to
  the Caller, then the player's bids in order (Pass, Fleck, Schnapser, …).
- **Bid buttons** name the game only ("Schnapser", "Lomt"). A call whose
  chance of success is above 20% shows it, e.g. "Schnapser 43%". The
  chances come from a pre-computed table (`server/schnaps_web/game/
  success_table.json`): per hand class and seat, the success chance the
  contract network's value head predicted in the round-2 measurements
  (Docker/forced-contract-option.md). Rebuild it with
  `python3 scripts/build_success_table.py ~/schnaps_forced_measure_lomt.json
  ~/schnaps_forced_measure_bauern.json ~/schnaps_forced_measure_schnapser_r2.json`.
  Jodler and Hermort have no table (they win at once).
- **Bots** get a random Harry Potter first name, a different one per seat;
  the seat list says which bot it is ("Hermione (Firenze bot)").
- **20 and 40:** a declaration shows on the green table over the trick it
  leads ("Anna: 40 ♥ Herz"), and next to the player's name for the rest of
  the deal.
- **Three bots: Bologna, Firenze and Verona** (in the code and the docs:
  Basic, Large and 2a). Bologna and Firenze share the bidder and the
  Schnapser, Lomt and Bauern networks. They differ in the Normal-game
  network: Bologna has the compact one trained on the laptop, Firenze the
  bigger one trained on a rented GPU (Docker/gpu-training.md, step 4).
  Verona has the same bidder, but ONE network, trained on a GPU on every
  contract at once, plays the cards in every game (step 2a,
  Docker/step2a-options.md). Over full deals Verona beat Firenze by +0.20
  ± 0.05 points per deal.
- **When a deal ends early** (a Jodler or Hermort lost, a Schnapser that
  missed a trick, a resignation) everyone sees the cards still in hand.
- **Both bots bid with the set in mind.** It values a bid only by
  the points that still count for the set. It flecks only when the fleck
  can't cost the set (the other side needs no more points than the contract
  is worth, e.g. 9 or less against a Lomt), or when it's at least 75% sure.
- **Between deals:** the result shows for 5 seconds, then the next deal
  starts.
- **Disconnects:** the table waits for the player to come back. Reloading
  the page, or reopening it in the same browser, returns you to your seat.

Your seat is protected by a private token kept in your browser (an
account only decides which name you sit down with). On the main port
(8000) nobody, including spectators, can see another player's cards.

**The all-cards watch port (8001).** <http://localhost:8001> shows the same
lobby and tables, read-only, with **every hand face up**. Nothing can be
changed from there (no seats, no moves). Anyone who can open it sees all
cards, so only forward it to the LAN when nobody playing would peek.
`SCHNAPS_WEB_WATCH_PORT` picks another port; `0` turns it off.

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

3. **Start the site.** It takes about a minute while the three
   players load and compile. Then open <http://localhost:8000> (and the
   all-cards watch page on <http://localhost:8001>). Ctrl-C stops it.

   ```powershell
   wsl -d Ubuntu -- bash /mnt/c/Users/marco/Documents/git/Docker/schnaps-web/scripts/start_site.sh
   ```

   Accounts and ratings are kept in `data/db/` (created on first use) and
   survive restarts. `SCHNAPS_WEB_DB_DIR=<dir>` keeps them elsewhere; an
   empty value keeps them in memory only. To start the ratings over, stop
   the site and delete `data/db/ratings.json` and `data/db/sets.jsonl`
   (deleting `users.json` removes the accounts too).

The Basic player is in `models/basic_player`. To rebuild it from the
trained networks in `~`, run `scripts/build_model.sh --overwrite`. It uses:

- `~/schnaps_normal@4000` for the Normal game;
- `~/schnaps_forced_lomt@1000` and `~/schnaps_forced_bauern@1000`;
- `~/schnaps_forced_schnapser_r2@500` for Schnapser. This network was
  retrained after the rule change (the deal ends at the defenders' first
  trick), so its win estimate, which drives the bid, matches the new rule.

`--part <name>=<checkpoint>` swaps one part's network.

The Large player is in `models/large_player`: `scripts/build_large.sh
--overwrite` builds it with the same parts except the Normal network,
`~/schnaps_normal_big_gpu@1000` (`LARGE_NORMAL=<dir>@<step>` picks another).
The site offers Large only when that folder is built.

The 2a player is in `models/mixed_player`: `scripts/build_mixed.sh
--overwrite` builds it from `~/schnaps_mixed_big_gpu@500`, the one network
of step 2a (`MIXED_NET=<dir>@<step>` picks another checkpoint). It loads
as arch `schnaps_web.player_one` (`game/player_one.py`): the site player,
with the same network in all four parts, run once per move. The site
offers 2a only when that folder is built.

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

The watch port works the same way, with 8001 in place of 8000 (and its own
firewall rule, e.g. "Schnaps watch").

To undo both settings:

```powershell
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
Remove-NetFirewallRule -DisplayName "Schnaps site"
```

Anyone on your network can open the site and play as a guest; the
account passwords only protect names and ratings (the site uses plain
HTTP, so they are not secret on the network: don't reuse a real
password). Keep the firewall rule on the **Private** profile, so it
applies only on your home network.

**On a phone, hold it sideways.** In landscape (any screen at most 500 px
tall) the felt fills the screen under a slim header and scales to fit, down
to 640 × 360; the call buttons, the deal's result and the Show/Resign bar
float over the felt, and the scoreboard, seats and score sheet are below it.
Held upright, the page asks you to turn the phone. (CSS: the `max-height:
500px` blocks at the end of `site.css` and `gui/games/schnaps/schnaps.css`.)

## Tests

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/marco/Documents/git/Docker/schnaps-web/scripts/test.sh
```

They cover:

- scoring, sets, the match and dealer rotation (`tests/test_match.py`);
- whole deals and the privacy of each seat's view (`tests/test_deal.py`);
- bids in the view, call labels and their chances, the all-cards reveal
  (`tests/test_deal.py`);
- the API and WebSocket: seats, permissions, privacy, a human move, a
  complete match between bots, bot names, and the read-only watch app
  (`tests/test_app.py`);
- each table's language: Italian by default, carried to the lobby list,
  players, spectators and the watch app (`tests/test_lang.py`);
- accounts, device keys, the database files, Elo, which sets are rated
  (guests, seat changes, the same pair), the set log and a rated bots-only
  match (`tests/test_ratings.py`);
- the accounts a device remembers and who plays in a tab
  (`client/src/net/accounts.test.ts`), rating labels and the account
  errors (`client/src/table/labels.test.ts`);
- the translation table (`client/src/i18n/strings.test.ts`, run with
  `node --test`; `test.sh` runs it after the server tests when it gets no
  arguments): every string in every language with the same parameters, the
  Italian card names, Pass/Weiter/Via, move buttons and server errors.

## Languages

The site speaks **Italian** (preselected), **German** and **English**
(the base language: a missing translation falls back to it).

- **The language belongs to the table.** Pick it in the lobby before
  **Start table**. Everyone at that table, players and spectators (also on
  the watch port), sees that language. The lobby shows the language picked
  there, and the browser remembers it for the next table.
- **Game terms:** Italian and English keep the German names of the suits
  (Herz, Caro, Pik, Kreuz), the contracts (Schnapser, Lomt, Bauern, Jodler,
  Hermort, Normal) and Fleck. Pass is **Weiter** in German and **Via** in
  Italian. The Italian ranks are Asso, Dieci, Re, Cavallo and Nižek (Unter;
  the Slovenian name used in Val Canale).
- **Where the strings are:** all of them are in
  `client/src/i18n/strings.ts`. The server stays language-neutral: it sends
  card codes, action ids, contract names, bids ("Pass") and English error
  messages, and the client translates them. Move buttons are built from the
  action id. Server errors are matched against the `err…` keys.

**To add a string:**

1. Add a key to `STRINGS` in `client/src/i18n/strings.ts` with `en`, `de`
   and `it`. Write a parameter as `{name}`, the same in all three.
2. Show it with `t(lang, 'key', {name: value})`, or in a component under the
   table page with `const tr = useT(); tr('key', {name: value})`
   (`client/src/i18n/lang.tsx`).
3. If the server sends a new error players can trigger, add an `err…` key
   whose `en` is exactly the server's text (`{x}` stands for a value).
4. Run `scripts/test.sh` and rebuild the client.

A new language: add it to `Lang`, `LANGS` and `LANG_NAMES` in
`strings.ts`, give every entry a translation for it (TypeScript lists the
missing ones), and add it to `LANGS` in `server/schnaps_web/table.py`.

## Layout

```
server/schnaps_web/
  app.py        FastAPI: REST API, a WebSocket per table, serves client/dist
  lobby.py      the tables (in memory: they are gone when the server restarts)
  table.py      seats, tokens, the life cycle, the bot driver, rating sets
  match.py      sets, matches, dealer and seat mapping (pure)
  rating.py     pair keys and Elo (pure)
  db.py         users, pair ratings and the set log, as files in data/db/
  deal.py       one deal on the pyspiel engine; each seat's view
  bots.py       the bot catalog (Bologna, Firenze, Verona; Random for tests)
  config.py     settings
  game/         copied from the development tree (see below)
  tools/        build_player.py: assembles a player in models/
client/src/
  i18n/         every string in Italian, German and English; the lookup
  lobby/        the lobby page (language picker, player card, ratings)
  table/        the table page: scoreboard, seats, result, score sheet
  net/          REST calls, the table's WebSocket, remembered accounts
  gui/          the table UI, copied from the OpenSpiel GUI
models/basic_player/    the Basic player (four networks plus the bidder)
models/large_player/    the Large player (the bigger Normal network)
models/mixed_player/    the 2a player (one network for every contract)
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
| `models/basic_player/` | built from `~/schnaps_normal@4000`, `~/schnaps_forced_{lomt,bauern}@1000` and `~/schnaps_forced_schnapser_r2@500` |
| `models/large_player/` | the same, with `~/schnaps_normal_big_gpu@1000` for the Normal game |
| `models/mixed_player/` | built from `~/schnaps_mixed_big_gpu@500` (step 2a), one network for every contract |

Still used as installed libraries (not copied):

- the pyspiel game engine, `schnaps(max_flecks=2)`;
- the OpenSpiel scale framework, which loads and runs the networks.

Both come from `Docker/open_spiel` (its venv and `build/python`).

## Not done yet

- Elena as a selectable bot: one entry in `bots.py`.
- Saving tables across restarts (accounts and ratings are saved).
- A real database (the JSON files are fine for a family LAN).
- A history page from the set log (`data/db/sets.jsonl`).
- Docker packaging.
- Chat.
