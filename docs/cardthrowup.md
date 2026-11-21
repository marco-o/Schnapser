# cardthrowup: throwing your cards on the table (proposal, 2026-11-21)

Status: discussion only. Nothing is built.

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
