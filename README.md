# FAA attribution forecaster — polymarket-faa-attribution-02

Entry for make.fun's `polymarket-faa-attribution-02`: forecast, for every
market of the family and each of the 240 minutes after a checkpoint, five
quantiles (5/25/50/75/95%) of that minute's Yes price. Scored by mean
pinball loss; runs offline, stdlib-only Python, no model calls.

## Model

Per market: the empirical distribution of h-minute price changes over
the case's own history (exponentially decay-weighted, half-life 720
minutes), read off at 28 anchor horizons and interpolated in log-h.
The median offset is pinned to zero (persistence median); the spread is
scaled by 0.65, the two tail quantiles are widened a further 1.35x, and
every spread is multiplied by a cross-market regime factor (last hour's
realized movement vs its 24-hour rate, clipped to [0.7, 1.5]). Every
forecast value is snapped to a price level the market actually printed
in its last 1440 minutes.

When a case is one mutually-exclusive candidate family (many markets
whose Yes prices sum to ~1), a conditioning step mean-reverts the sum
of medians toward the present markets' share of the universe. The FAA
final's cases are a few independent questions instead, so the step is
guarded: it runs only on cases with at least 8 markets and a checkpoint
sum in [0.6, 1.6].

## Validation (local, kit's practice cases)

The practice cases are cut from Polymarket's "Next CEO of NVIDIA?"
event. Rebuilding their inputs from the public CLOB price history
reproduces the kit files exactly (0 differing points out of 214,513),
and the house baseline scored through the local replica of the scorer
lands on the kit's stated 0.363589 to all six decimals. This entry
scores **0.269483** on the same six cases through the same replica.

## Layout

- `main.py` — the whole forecaster (the graded entrypoint).
- `TUNING.md` — what was adapted for this competition, and why.
