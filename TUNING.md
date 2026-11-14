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
