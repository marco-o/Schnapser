# cardthrowup: throwing your cards on the table (2026-11-21)

Status: **built, then revised** (2026-11-21). **§8 is the current
design: Allmine is gone, and a Show button lets a player lay their hand
open to the opponents only.** §1–§7 are the history: the first proposal,
the user's answers and the first as-built notes.

In human games a player sometimes lays their cards open because the outcome
is clear to them. It has two meanings:

- **Resign:** "no point going on, you win". It is always accepted.
- **Allmine:** "I take every trick from here". The opponents check it.
  - It is common in a Lomt, where the declarer can see from the start that
    every trick is theirs.
  - It can come later, for example once someone has played the only card
    that could have caused trouble.

Both end the deal early. This file collects how the site could do this, and
the questions to settle before building it.

## 1. What each throw means for the score

The clean way to define both is through the remaining tricks:

| Throw | By | Means | Contract | Normal game |
|---|---|---|---|---|
| Allmine | either side | my side takes every remaining trick | declarer side: made; defenders: failed (their first trick already ends it, so it is only useful on the last tricks) | play-out (below) |
| Resign | declaring side | the contract fails | failed: stake × 2^flecks to the defenders | — |
| Resign | defenders | the contract is made | made | — |
| Resign | either side in a Normal game | the other side wins the game now | — | rule (below, open question) |

- **Allmine in a Normal game:** the server plays the deal out along a line
  in which the claiming side takes every trick (the solver below finds it).
  So the engine scores it exactly, including 66, 20/40 declarations and
  Schneider/Schwarz.
- **Resign in a Normal game can't be played out:** the resigner may hold
  cards that must win a trick (say the trump As). It needs a scoring rule.
  Proposal: the other side wins as if it had just reached 66. That gives 3
  if the resigners have no trick, 2 if they are under 33 points, else 1. It
  is the engine's own Normal-game rule, applied at the moment of the throw.

## 2. Checking an Allmine

The server knows all four hands, so it can check a claim exactly and
instantly. Nobody has to check by hand.

- **Solver:** `PlaySolver` in open_spiel `envs/schnaps_oracle.py`. It is
  alpha-beta with a transposition table, pure Python, and tested move for
  move against pyspiel.
  - The claim is valid when the claiming partnership can force every
    remaining trick against any defence, with all hands known. That
    matches the human practice: the opponents check against their own
    cards.
  - Copy it into the site tree (the site's copy-not-import rule), like
    bidding.py.
- **Cost:** at most 5 tricks are left, and a refuted line stops at the
  first trick lost. From the very start of a Lomt (20 cards) it needs a
  timing check, but the oracle already solved whole deals in bulk for the
  hand weights.
- **A subtlety:** the solver accepts the claim if *a* winning line exists,
  even one the claimant didn't see. Humans usually accept a shown hand on
  that basis too.

**A wrong claim.** A table option, to decide:

- **Lenient (proposed default for family play):** the claim is refused,
  and the claimant's hand stays face up for the rest of the deal. That is
  what happens at a real table when the opponents say "play it out".
- **Strict:** a wrong claim counts as a resignation.

## 3. UI

A permanent action bar under the player's hand during the play, with two
buttons:

- **Resign:** shown from the third trick, as suggested. In a contract the
  declaring side may want it earlier (for example in a Lomt when the first
  lead goes wrong), so maybe from the first card there (open question).
  It asks to confirm, as it can't be undone.
- **Allmine:** shown during the whole play, from before the first lead (so
  a Lomt can be claimed at once).
  - **It must not appear only when the claim is valid.** That would tell
    the player they have a forced win they hadn't noticed. The button is
    always there, and the server checks on press.

After a throw:

- the thrower's cards turn face up for everyone, with a banner ("Anna
  claims all tricks", "Anna resigns");
- for Allmine, the server's verdict follows at once ("checked: all tricks
  are hers", or "refused: Ron's trump Ober takes a trick", without
  revealing more than the rule needs);
- then all hands are shown for the usual pause, as at the end of a deal,
  and the next deal starts.

The watch app (port 8001) shows the same events.

## 4. Bots

- **Accepting:** nothing needed. The server's check stands in for the
  opponents.
- **Claiming:** a bot could claim when the solver proves all tricks. That
  makes bot deals end sooner and feels natural. It means one solver call
  per bot turn in the play, with a time cap (or only from trick 2 on).
- **Resigning:** probably never. A bot loses nothing by playing on, and
  resigning could look odd. An option for later: resign when the solver
  proves the deal lost.

## 5. Server outline

- **`deal.py`:**
  - `Deal.resign(seat)` and `Deal.claim(seat)`. They end the deal with an
    outcome (returns[4], contract, declarer, flecks) instead of a terminal
    pyspiel state.
  - `result()` returns that outcome when it is set.
  - For Allmine in a Normal game, the play-out line is applied as real
    moves, so the state becomes terminal the usual way.
- **`table.py`:**
  - new actions next to `act()`, the same checks (seat, phase);
  - `_drive` stops the bots once the deal has an outcome, and
    `_finish_deal` records it through `match.record` as today.
- **`game/view.py`:**
  - the frame carries the throw (who, which, verdict) and the shown hands;
  - the event goes into the deal log.
- **Client:**
  - the action bar in `client/src/table/table_page.tsx`;
  - the banner and open cards in the table renderer;
  - labels in `table/labels.ts`.
- **Tests:**
  - scoring of each row of the table in §1;
  - a claim refused and accepted, and a Lomt claimed before the first lead;
  - resign availability by trick;
  - bots never stall after a throw;
  - the frame doesn't leak hidden cards before the throw.

## 6. Questions to settle first

1. The Normal-game resign score: "as if they reached 66 now" (above), or
   always 3, or something from the house rules?
2. In a Normal game, does one player resign for the pair, or must the
   partner confirm?
3. When is Resign offered: from trick 3 everywhere, or earlier for the
   declaring side of a contract?
4. A wrong Allmine: lenient (refused, hand stays open) or strict (counts as
   resign)? A table option with which default?
5. Should bots claim? Should they ever resign?
6. Is the Allmine verdict shown with the reason (the card that would take a
   trick), or just "refused"?

### Answers (the user, 2026-11-21)

1. **Normal-game resign:** "as if they reached 66 now": the other pair
   wins 3 if the resigners have no trick, 2 if they are under 33 points,
   else 1 (times 2^flecks). Contracts score their stake as in §1 (a failed
   Schnapser 6, Lomt 9, …, times 2^flecks).
2. **One player decides** for the pair; no partner confirmation.
3. **Resign is offered** during the whole play in a contract (either
   side), and from the third trick in a Normal game.
4. **A wrong Allmine is always strict:** it counts as a resignation by the
   claimant. No table option.
5. **Bots claim** Allmine when the solver proves it. Bots never resign.
6. **The verdict shows the reason** (the card that would take a trick).

## 7. As built (2026-11-21)

### Rules as implemented

| Throw | When offered | Scored |
|---|---|---|
| Resign, contract | the whole card play, any seat, also out of turn | declaring side resigns: failed, stake × 2^flecks to the defenders; a defender resigns: made |
| Resign, Normal game | from the third trick (2 tricks done) | the other pair as if it had just reached 66: 3 if the resigners have no trick, 2 if under 33 points, else 1; × 2^flecks |
| Allmine, holds | the whole card play (from before the first lead), any seat, also out of turn | the solver's line is played out on a copy of the pyspiel state; the engine's returns score it (66, 20/40, Schneider/Schwarz, flecks) |
| Allmine, wrong | same | strict: counts as a resignation by the claimant, whatever the trick (so also before trick 3 in a Normal game) |

- **What "holds" means:** the claimant's partnership can force every
  remaining trick against any defence with all hands open, and that line
  wins the deal for it. A trick won by the *partner* in a Lomt/Bauern (only
  the declarer may take tricks there) or a Schnapser that ends at trick 3
  under 66 is not a win, so such a claim is refused too.
- A defender's claim in a contract is checked the same way: their first
  trick ends the deal, so it holds when they can force taking the next
  trick before the declarer's side makes it.
- A throw ends the deal at once. The state stays as it was at the throw,
  so every hand shows face up to everyone (all four seats, spectators and
  the watch port) for the usual deal pause.
- **Bots:** before each bot move in the card play the table asks the
  solver whether the bot's pair can claim (a null-window search, capped at
  `table.BOT_CLAIM_BUDGET` = 50,000 nodes); if so the bot claims. Bots never
  resign, so a bot's throw is always an accepted Allmine.
- **Confirm step:** Resign *and* Allmine ask to confirm (Allmine too,
  because a wrong claim counts as resigning, and a stray tap would cost
  the deal).

### Where it lives

- `server/schnaps_web/game/oracle.py`: the card-play part of open_spiel's
  `envs/schnaps_oracle.py` copied unchanged (Rules, play_legal, play_apply,
  PlaySolver), plus:
  - `ClaimSolver`: PlaySolver's alpha-beta with a changed value (a trick
    won by the other side is `LOST` = -1000, below every score), so the
    defence refutes a claim whenever it can; `value`, `holds` (null
    window, optional node budget), `line` (best play for both sides,
    lowest action id among equals).
  - `first_lost_trick`: the card and seat that take the first trick on a
    refuting line (the reason shown).
  - `position(state)`: the pyspiel state as a play tuple, replayed from
    the history and checked against the state's text (hands, score,
    tricks, player to move).
- `deal.py`: `Throw` (kind, game seat, accepted, reason, trick, returns),
  `Deal.resign / claim / claim_holds / can_resign / can_claim / in_play`;
  `is_over`, `to_move`, `frame` and `result` honour the throw. The frame
  gains `"throws": {"resign", "allmine"}` (what the viewer is offered;
  all false for spectators and outside the play).
- `game/view.py`: `present(..., throw=)` puts the throw into the view as
  `"throw"` (and shows every hand, phase "terminal", nobody to move);
  `throw_text` gives the log name ("Resign", "Allmine", "Allmine
  refused").
- `table.py`: `Table.throw(token, kind)` (same seat/phase checks as
  `act`), bot claims in `_drive` (which also skips a bot move whose deal
  was thrown while the bot thought), the throw recorded through
  `match.record` into `DealResult.throw` ({kind, table seat, accepted,
  text}).
- `app.py`: `POST /api/tables/{id}/throw {kind: "resign" | "allmine"}`.
- Client: `table/throw_bar.tsx` (`ThrowBar`: the bar under the hand, a
  `.site-felt__actions` bar, so on phones it floats over the felt;
  `ThrowNotice`: "Anna claims all remaining tricks · Checked…" or
  "Refused: Ron's Pik As takes a trick. It counts as resigning.";
  `throwMark` for the score sheet, e.g. "Normal · allmine (Vernon)"),
  `net/api.ts` (`throwCards`, the types), strings in `i18n/strings.ts`
  (en/de/it, incl. the three new server errors), CSS under `.site-throw`
  in `site.css`.

### Cost

Timed on 2,592 positions of random deals (every trick, mid-trick too):
the slowest exact claim check took 33 ms (4,884 nodes, a Normal game
before the first lead); a Lomt from the start took 16 ms. So claims are
solved inline, without a worker thread.

### Tests

`server/tests/test_cardthrowup.py` (15 tests): resign scoring in each
contract (both sides, with and without flecks) and in a Normal game; when
Resign/Allmine are offered (trick 0/1/2/3, contracts, bidding,
spectators); Allmine accepted (score = the solver's value), refused
(counts as resign, reason card from an opponent's hand), a Lomt claimed
before the first lead by the declarer and by a defender; the claim solver
against a brute-force search; the bots' node budget; frames before (no
leak) and after a throw (every hand, no moves); over the API, a throw
recorded and the table playing on; a full bot match where bots claim and
never resign.

Checked end to end in the browser (2026-11-21): a bot partner's accepted
claim after the first card, Resign of a Lomt from the first card, and a
refused Normal-game Allmine before the first lead with its reason.

## 8. Revision: Show instead of Allmine (2026-11-21)

**Why.** In testing, the bots claimed Allmine where a person would not:
- **A defender's claim was really one trick.** The defenders of a contract
  end it with their first trick, so for them "every remaining trick" meant
  just the next one, with nothing certain about the whole game.
- **A Schnapser was claimed from three sure tricks.** The solver, seeing
  every hand, could prove 66 when no player could see it from their own
  cards.

The user decided: **remove Allmine, keep Resign, and add Show**.

**Show.**
- During the card play, any seated player may lay their hand open to the
  **two opponents only**: not to the partner, not to spectators. The
  all-cards watch port still sees everything.
- Play goes on. The hand stays open to the opponents for the rest of the
  deal, as it is played down. Once per seat and deal; it can't be undone,
  so it asks to confirm.
- The purpose is that the opponents can see the deal is lost and resign.
  So once an opponent has shown, **Resign is offered at once**, even in a
  Normal game before the third trick. Otherwise Resign is unchanged: the
  whole play in a contract, from the third trick in a Normal game.
- Everyone at the table gets a notice: "Anna shows their cards to the
  opponents".
- Bots never show and never resign. They also ignore shown cards: their
  networks have no input for them.

**What changed in the code.**
- `deal.py`:
  - `Deal.show` and `can_show`, with `Deal.shown` (game seats);
  - `can_resign` opens for the side whose opponent has shown;
  - `Throw` is a resignation only;
  - claim, `claim_holds` and `can_claim` are gone.
- `game/view.py`: `present(..., shown)` opens a shown hand to the other
  partnership, and the view carries `"shown"`.
- `game/oracle.py`: the claim solver (`ClaimSolver`, `Budget`,
  `first_lost_trick`) is removed. The card-play copy and `position` stay,
  for Resign's scoring.
- `table.py` and `app.py`:
  - a new `POST /api/tables/{id}/show`;
  - `throw` accepts only `"resign"`;
  - the bots' Allmine check is gone.
- Client:
  - `throw_bar.tsx` has Show and Resign, and the notices;
  - Allmine strings removed, Show strings added (it/de/en);
  - `frame.throws` is `{resign, show}`.

**Tests.** `server/tests/test_cardthrowup.py`:
- a shown hand opens to the opponents only (not the partner, not
  spectators), once per deal, and stays open as it is played down;
- an opponent of a shower may resign at once in a Normal game's first
  trick;
- Show and Resign over the API;
- bots never throw in a whole match.

All 61 server tests and 8 client tests pass. It was checked in the browser:
an opponent sees the shown hand face up, with the notice and Resign.
