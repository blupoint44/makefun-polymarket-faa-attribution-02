#!/usr/bin/env python3
"""Quantile forecaster for make.fun polymarket-faa-attribution-02.

Carried over from our Nvidia CEO forecast entry (same program/v1 protocol,
same pinball scoring, practice cases cut from the same Nvidia event) with
one structural adaptation for this competition's final: the FAA family is
four INDEPENDENT Yes/No questions (one per attribution, each its own
event), not one mutually-exclusive candidate family. The round-3
cross-market sum conditioning below assumes a partition family whose Yes
prices sum to ~1 across a 24-market universe, so it is now applied only
when a case actually looks like such a family (>= MIN_PARTITION_MARKETS
markets in the case). On a small independent-question case the plain
per-market model runs, exactly as our round-2 model did.

Base model (unchanged recipe, tuned on Polymarket history and
headline-checked on official practice cases):

For each market, take the last RECENT minutes of its price history and,
for each anchor horizon h, the empirical distribution of h-minute price
changes p[i+h]-p[i], with exponential time-decay weights (half-life HL
minutes). The 5 scored quantiles of that distribution are the forecast
offsets at h. The median offset is forced to zero (persistence median),
the remaining spread is scaled by WIDTH, and the two tail quantiles
(0.05 / 0.95) get an extra TAU_MUL widening. All spreads are then scaled
by a cross-market regime factor: the ratio of the last hour's mean
absolute 1-minute movement (summed over the case's markets) to its
24-hour rate, clipped to [0.7, 1.5]. Each forecast value is snapped to
the nearest price level actually observed in the market's last 1440
minutes. Offsets for non-anchor minutes are interpolated linearly in
log-h. Forecast = clamp(x + offset) rounded to 6 decimals, snapped, rows
forced non-decreasing.

Partition-family conditioning (only when the guard passes): the sum of
medians mean-reverts from the checkpoint sum toward n_markets /
UNIVERSE_N, allocated by price share with approach rate 1-exp(-h/180),
and shifted values are re-snapped to each market's observed levels.

Deterministic, stdlib only, no network. Any per-market failure falls
back to the plain house-baseline forecast for that market, so the
output shape is always valid.
"""
import json
import math
import os
import sys

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

TAUS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.644854, -0.67449, 0.0, 0.67449, 1.644854]
BASE_SIGMA = 0.0025

ANCHORS = [1, 2, 3, 4, 5, 6, 7, 9, 11, 13, 16, 19, 23, 27, 32, 38, 45, 53,
           62, 73, 85, 99, 115, 133, 154, 178, 205, 240]
LOG_ANCHORS = [math.log(a) for a in ANCHORS]
RECENT = 4320        # minutes of history used per market
HL = 720.0           # decay half-life of change samples, minutes
WIDTH = 0.65         # scale on empirical spread around the median
TAU_MUL = [1.35, 1.0, 1.0, 1.0, 1.35]  # per-tau multiplier (tails widened)
CAP = 900            # max change samples per anchor
SNAP_WINDOW = 1440   # minutes of history defining the price lattice
REGIME_WIN = 60      # minutes of realized movement for the regime factor
REGIME_BASE = 1440   # baseline window the regime factor is measured against
REGIME_CLIP = (0.7, 1.5)

# Cross-market sum conditioning (partition families only). The markets
# in such a case are mutually exclusive outcomes, so the sum of last
# prices S0 should track the present markets' share of the full
# universe, target = n_markets / UNIVERSE_N. The checkpoint sum
# mean-reverts toward that target; every non-fallback market's whole
# quantile row is shifted by the implied sum path, allocated in
# proportion to its price share, with approach rate 1 - exp(-h/REV_TAU).
UNIVERSE_N = 24
REV_TAU = 180.0
# A case with fewer markets than this cannot be a slice of the
# 24-market partition family this conditioning was tuned on; small
# families (the FAA final's independent questions) skip it entirely.
MIN_PARTITION_MARKETS = 8


def price6(v):
    r = round(min(1.0, max(0.0, v)) * 1e6) / 1e6
    return r + 0.0  # avoid -0.0


def baseline_rows(x, horizon):
    rows = []
    for h in range(1, horizon + 1):
        s = BASE_SIGMA * math.sqrt(h)
        rows.append([price6(x + z * s) for z in Z])
    return rows


def weighted_quantiles(sorted_vals, sorted_w):
    """Quantiles at TAUS by cumulative-weight linear interpolation."""
    tot = sum(sorted_w)
    n = len(sorted_vals)
    if n == 0 or tot <= 0:
        return [0.0] * 5
    out = []
    cum = 0.0
    j = 0
    for tau in TAUS:
        target = tau * tot
        while j < n - 1 and cum + sorted_w[j] < target:
            cum += sorted_w[j]
            j += 1
        wj = sorted_w[j]
        frac = 0.0 if wj <= 0 else min(1.0, max(0.0, (target - cum) / wj))
        lo = sorted_vals[j]
        hi = sorted_vals[j + 1] if j + 1 < n else lo
        out.append(lo + frac * (hi - lo))
    return out


def anchor_offsets(prices, regime_scale):
    """Per-anchor 5 offsets: median-zeroed, width-scaled, per-tau widened,
    regime-scaled."""
    n = len(prices)
    decay = math.exp(math.log(0.5) / HL)
    # powers[i] = decay**i, built once
    powers = [1.0] * n
    for i in range(1, n):
        powers[i] = powers[i - 1] * decay
    offs = []
    for h in ANCHORS:
        m = n - h
        if m <= 0:
            offs.append([0.0] * 5)
            continue
        stride = max(1, m // CAP)
        pairs = []
        for i in range(0, m, stride):
            # weight by age of the end of the step: recent ends weigh more
            pairs.append((prices[i + h] - prices[i], powers[n - 1 - (i + h)]))
        pairs.sort(key=lambda p: p[0])
        sv = [p[0] for p in pairs]
        sw = [p[1] for p in pairs]
        q = weighted_quantiles(sv, sw)
        med = q[2]
        offs.append([(q[j] - med) * WIDTH * TAU_MUL[j] * regime_scale
                     for j in range(5)])
    return offs


def snap_level(levels, v):
    """Nearest observed price level to v (levels sorted, non-empty)."""
    import bisect
    i = bisect.bisect_left(levels, v)
    best, bestd = None, None
    if i < len(levels):
        best, bestd = levels[i], abs(levels[i] - v)
    if i > 0 and (bestd is None or abs(levels[i - 1] - v) < bestd):
        best = levels[i - 1]
    return best if best is not None else v


def _mv(prices, win):
    """Mean absolute 1-minute movement over the last win minutes."""
    n = len(prices)
    w = min(win, n - 1)
    if w <= 0:
        return 0.0
    s = 0.0
    for i in range(n - w, n):
        s += abs(prices[i] - prices[i - 1])
    return s / w


def regime_scale(all_prices):
    """Cross-market regime factor: last-hour realized movement vs its
    24-hour rate, summed over markets, clipped to REGIME_CLIP."""
    num = sum(_mv(p, REGIME_WIN) for p in all_prices)
    den = sum(_mv(p, REGIME_BASE) for p in all_prices)
    if den <= 0 or num <= 0:
        return 1.0
    r = num / den
    lo, hi = REGIME_CLIP
    return min(hi, max(lo, r))


def interp_rows(offs, horizon):
    rows = []
    for h in range(1, horizon + 1):
        if h <= ANCHORS[0]:
            rows.append(list(offs[0]))
            continue
        if h >= ANCHORS[-1]:
            rows.append(list(offs[-1]))
            continue
        lh = math.log(h)
        k = 0
        while ANCHORS[k + 1] < h:
            k += 1
        f = (lh - LOG_ANCHORS[k]) / (LOG_ANCHORS[k + 1] - LOG_ANCHORS[k])
        rows.append([offs[k][j] + f * (offs[k + 1][j] - offs[k][j]) for j in range(5)])
    return rows


def forecast_market(prices, horizon, regime=1.0):
    x = prices[-1]
    if len(prices) < 60:
        return baseline_rows(x, horizon)
    levels = sorted(set(prices[-SNAP_WINDOW:]))
    offs = anchor_offsets(prices[-RECENT:], regime)
    rows = interp_rows(offs, horizon)
    out = []
    for row in rows:
        r = [price6(snap_level(levels, price6(x + o))) for o in row]
        for j in range(1, 5):
            if r[j] < r[j - 1]:
                r[j] = r[j - 1]
        out.append(r)
    return out


def apply_sum_conditioning(all_rows, all_prices, fallback, horizon):
    """Shift non-fallback markets' rows so the sum of medians follows the
    mean-reverting sum path toward n_markets / UNIVERSE_N. Mutates all_rows
    in place; re-snaps shifted values to each market's observed levels."""
    n_mk = len(all_prices)
    if n_mk == 0:
        return
    xs = [p[-1] if p else 0.0 for p in all_prices]
    s0 = sum(xs)
    gap = s0 - n_mk / UNIVERSE_N
    if gap == 0.0:
        return
    share_sum = sum(x for x, fb in zip(xs, fallback) if not fb)
    if share_sum <= 0:
        return
    for idx, (rows, prices, fb) in enumerate(zip(all_rows, all_prices, fallback)):
        if fb:
            continue
        share = xs[idx] / share_sum
        if share == 0.0:
            continue
        levels = sorted(set(prices[-SNAP_WINDOW:]))
        if not levels:
            continue
        for h in range(1, horizon + 1):
            ds = -(1.0 - math.exp(-h / REV_TAU)) * gap * share
            if ds == 0.0:
                continue
            r = [price6(snap_level(levels, price6(v + ds))) for v in rows[h - 1]]
            for j in range(1, 5):
                if r[j] < r[j - 1]:
                    r[j] = r[j - 1]
            rows[h - 1] = r


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    for fn in files:
        cid = fn[:-3]
        with open(os.path.join(INPUT_DIR, fn), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        horizon = int(case.get("horizon_minutes", 240))
        all_prices = [[float(p) for p in mk["prices"]] for mk in case["markets"]]
        try:
            regime = regime_scale(all_prices)
        except Exception:
            regime = 1.0
        all_rows, fallback = [], []
        for mk, prices in zip(case["markets"], all_prices):
            fb = len(prices) < 60
            try:
                q = forecast_market(prices, horizon, regime)
            except Exception:
                q = baseline_rows(prices[-1] if prices else 0.5, horizon)
                fb = True
            all_rows.append(q)
            fallback.append(fb)
        # Sum conditioning only for partition-family cases; a handful of
        # independent questions (the FAA final) must not be dragged
        # toward a partition share they do not have. A partition case
        # also betrays itself in its checkpoint sum: the present
        # markets' Yes prices add up to roughly one whole probability.
        s0 = sum(p[-1] for p in all_prices if p)
        if len(all_prices) >= MIN_PARTITION_MARKETS and 0.6 <= s0 <= 1.6:
            try:
                apply_sum_conditioning(all_rows, all_prices, fallback, horizon)
            except Exception:
                pass
        forecasts = [{"id": mk["id"], "q": q}
                     for mk, q in zip(case["markets"], all_rows)]
        with open(os.path.join(OUTPUT_DIR, cid + ".out"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"forecasts": forecasts}) + "\n")


if __name__ == "__main__":
    main()
