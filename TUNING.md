# Adaptation notes — polymarket-faa-attribution-02

The base recipe is the one we ran in polymarket-nvidia-ceo-forecast-01
(empirical decay-weighted change quantiles at 32→28 anchors, persistence
median, width 0.65, tail multiplier 1.35, regime factor, lattice snap,
partition sum conditioning). It transfers unchanged because this
competition's protocol is identical (program/v1, 72h history, 240
minutes, 5 quantiles, pinball) and its practice cases are cut from the
same Nvidia event at the same six checkpoints — verified locally:
baseline through our scorer replica = 0.363589, the kit's stated value
to six decimals; this entry = 0.269483, the same number the recipe
scored on those cases in the Nvidia competition.

What had to change is the final, not the practice:

1. **The final's family is not a partition.** Nvidia's universe is 24
   mutually exclusive candidates; the FAA family is four independent
   Yes/No questions (Iran / foreign actor / hack / AI sandbox escape),
   each its own event. Their Yes prices have no sum target. The
   round-3 sum conditioning, tuned for the candidate partition, would
   drag a 4-market case's medians toward 4/24 ≈ 0.17 of total mass —
   a large, wrong shift.
2. **Guard added.** Conditioning now runs only when the case carries
   at least 8 markets AND the checkpoint sum of last prices lies in
   [0.6, 1.6] (a partition's signature). Practice cases (19–24 markets,
   sums ≈ 1.0–1.1) still take it; a small independent-question case
   runs the plain per-market model. Practice score is unchanged by
   the guard (0.269483 before and after).
3. Everything else — anchors, decay, width, tails, regime, snap —
   is event-agnostic (all statistics come from the case's own 72h of
   history), so nothing else was retuned for shot 1.

## v2 — small-family path tuned on the FAA family's own tape

The five attribution markets (Iran, hack, foreign actor, AI, AI
sandbox escape) opened 2026-11-13 ~21:35-23:00Z and repriced violently
(e.g. Iran 0.515 -> 0.018 overnight). Their CLOB price history was
fetched from Polymarket and cut into family pseudo cases (checkpoints
every 15 min, all five markets, histories from each market's start);
because the tape was only hours old, scoring used the truncated
60/120-minute rows of each forecast against the realized tape (the
harness's parametrized clone reproduced v1's numbers exactly before
any variant was trusted).

Pinball on the FAA tape, v1 partition settings vs variants:

    @60min   v1 1.0289 | drift-median 0.5: 0.9877 | + width 0.8: 0.9572
             | + tails 1.6: 0.9380 (shipped as the v2 small-family path)
    @120min  v1 0.9542 | drift-median 0.5: 0.9223 | + width 0.8: 0.9111
             | + tails 1.6: 0.9039 (house baseline: 0.9300)

So for cases with fewer than MIN_PARTITION_MARKETS markets the model
now keeps half the empirical median (those markets trend, unlike the
calm partition family), uses width 0.80 and tail multiplier 1.6. The
shipped file reproduces those exact numbers through its own code path
(0.937992 @60, 0.903898 @120), and the official practice score is
unchanged at 0.269483 because practice cases take the partition path.
v2 is shot 2; shot 3 stays in reserve.
