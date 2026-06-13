"""
Layer 2 — Crime scoring for Third Space Finder.

One of several venue-scoring layers (capacity, crime, shade, weather, transit, ...).
This module scores only the *crime* layer: how safe a venue (lat/lng) is to host a
public gathering *at a given time of day*, using the City of Somerville open crime
dataset.

Design decisions (see PRD Layer 2 + conversation):
  - Spatial unit = the venue's own 2020 census block. Blocks are ~100-200m in
    urban Somerville: far smaller than a ward/neighborhood, so we never penalize
    a whole neighborhood. (Anti-redlining: scoring is block + incident-type +
    time-of-day specific, never a neighborhood blanket label.)
  - Relevance: only crimes that bear on a crowd's safety count. Violent/personal
    and disorderly/weapons are weighted high. Property crime that affects whether
    you can leave your car / not get pickpocketed (MV theft, theft-from-vehicle,
    pocket-picking, purse-snatching) gets a moderate weight. Shoplifting, fraud,
    etc. count ~0.
  - Time gate: the Somerville data has no hour, only a `police_shift`
    (Day 8a-4p / Evening 4p-12a / Night 12a-8a). We match the event's shift.
  - Anti-one-off: two guards. (1) Empirical-Bayes shrinkage pulls low-count
    blocks toward the citywide baseline, so a single incident barely moves the
    score. (2) A saturating, baseline-normalized transform means you need a
    genuine *cluster* to score badly, not one event.

Data source: https://data.somervillema.gov/Public-Safety/Police-Data-Crime-Reports/aghs-hqvg
The dataset is privacy-aggregated: no lat/lng, only a 15-digit census block GEOID.
We map a venue's coordinates to its block via the US Census geocoder. Coverage is
2017-present; each incident is logged under its single most severe offense; the
`year`/`day_and_month` are *report* dates while `police_shift` is when the incident
*occurred* (so time-gating is occurrence-based, recency is report-based).

KNOWN LIMITATION — privacy masking (do not oversell this layer):
  Sensitive incidents have ALL time and location fields stripped (no block, no
  ward, no shift). That's ~12% of all rows, but it is heavily skewed toward the
  highest-severity crimes this model weights most: ~57% of "Crimes against Person"
  and 100% of Sex Offenses are de-localized. These rows are unavoidably dropped
  (they match no block and no shift), so the block-level score under-counts serious
  person-crime by construction. Treat this layer as a solid signal for property /
  disorder / lower-severity crime at a given block and time — NOT as a complete
  violent-crime risk measure. There is no fix at block+time granularity; the
  masking is the privacy protection.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field

import httpx
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Relevance weights
# ---------------------------------------------------------------------------
# Keyed by `offensetype`. The big "Larceny/Theft Offenses" bucket is handled
# separately by NIBRS offensecode (see LARCENY_CODE_WEIGHTS) because it mixes
# crowd-relevant pickpocketing with irrelevant shoplifting.

OFFENSE_WEIGHTS: dict[str, float] = {
    # Direct threats to people in a crowd
    "Assault Offenses": 1.00,
    "Robbery": 1.00,
    "Homicide Offenses": 1.00,
    "Kidnapping/Abduction": 0.90,
    "Human Trafficking Offenses": 0.90,
    "Weapon Law Violation": 0.80,
    "Sex Offenses": 0.70,
    # Public disorder — affects whether a gathering feels/stays safe
    "Disorderly Conduct": 0.50,
    "Arson": 0.50,
    "Driving Under The Influence": 0.40,
    # "Can I leave my car / not get pickpocketed" — moderate
    "Theft From Motor Vehicle": 0.50,
    "Motor Vehicle Theft": 0.50,
    # Mild disorder signals — small contribution
    "Destruction/Vandalism Property": 0.15,
    "Drug/Narcotics Offenses": 0.10,
    "Burglary/Breaking And Entering": 0.10,
    # Everything else (fraud, forgery, embezzlement, liquor, trespass,
    # family nonviolent, MV offenses, "all other", etc.) -> 0 by default.
}

# NIBRS larceny subtypes. The dataset stores e.g. "23C" for shoplifting.
LARCENY_CODE_WEIGHTS: dict[str, float] = {
    "23A": 0.60,  # Pocket-picking  -> crowd pickpocketing, very relevant
    "23B": 0.60,  # Purse-snatching -> crowd, relevant
    "23F": 0.50,  # Theft from motor vehicle (car safety)
    "23G": 0.30,  # Theft of MV parts/accessories
    "23H": 0.20,  # All other larceny
    "23D": 0.10,  # Theft from building
    "23C": 0.00,  # Shoplifting -> irrelevant to a watch party
    "23E": 0.00,  # Theft from coin machine
}
LARCENY_OFFENSETYPE = "Larceny/Theft Offenses"
LARCENY_DEFAULT_WEIGHT = 0.15  # unknown larceny subcode

# ---------------------------------------------------------------------------
# Tuning knobs
# ---------------------------------------------------------------------------
RECENCY_HALF_LIFE_YEARS = 2.0   # incidents lose half their weight every 2 yrs
SHIFT_MATCH_WEIGHT = 1.00       # incident in the event's shift
SHIFT_OFF_WEIGHT = 0.10         # incident in a different shift — faint signal of
                                # the block's general character; kept low so
                                # time-of-day dominates (a 2am-only problem block
                                # still scores well for a 6pm event).
SHRINKAGE_K = 2.0               # pseudo-observations at baseline (anti-one-off)
RISK_SCALE_PERCENTILE = 75      # block at this risk percentile scores 50
CURRENT_YEAR = 2026

SOCRATA_URL = "https://data.somervillema.gov/resource/aghs-hqvg.json"
CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"


# ---------------------------------------------------------------------------
# Shifts
# ---------------------------------------------------------------------------
def shift_for_hour(hour: int) -> str:
    """Map an event hour (0-23) to the dataset's shift label."""
    if 8 <= hour < 16:
        return "Day"
    if 16 <= hour < 24:
        return "Evening"
    return "Night"  # 0-7


def _normalize_shift(raw: str | float) -> str | None:
    """Parse the dataset's `police_shift` string into Day/Evening/Night."""
    if not isinstance(raw, str):
        return None
    s = raw.lower()
    if "day" in s:
        return "Day"
    if "evening" in s:
        return "Evening"
    if "night" in s:
        return "Night"
    return None


# ---------------------------------------------------------------------------
# Per-incident relevance weight
# ---------------------------------------------------------------------------
def relevance_weight(offensetype: str, offensecode: str | float) -> float:
    if offensetype == LARCENY_OFFENSETYPE:
        code = str(offensecode).strip().upper() if pd.notna(offensecode) else ""
        return LARCENY_CODE_WEIGHTS.get(code, LARCENY_DEFAULT_WEIGHT)
    return OFFENSE_WEIGHTS.get(offensetype, 0.0)


def recency_weight(year: int | float) -> float:
    try:
        age = max(0, CURRENT_YEAR - int(year))
    except (TypeError, ValueError):
        return 0.0
    return 0.5 ** (age / RECENCY_HALF_LIFE_YEARS)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_crime_incidents(cache_path: str | None = None) -> pd.DataFrame:
    """Load the Somerville crime dataset, from a local cache or live API."""
    if cache_path:
        if cache_path.endswith(".parquet"):
            return pd.read_parquet(cache_path)
        return pd.read_csv(cache_path, dtype={"blockcode": str, "offensecode": str})

    resp = httpx.get(
        SOCRATA_URL,
        params={
            "$select": "blockcode,offensetype,offensecode,police_shift,year",
            "$limit": 200000,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


# ---------------------------------------------------------------------------
# Risk index: weighted risk per (block, shift)
# ---------------------------------------------------------------------------
@dataclass
class CrimeRiskIndex:
    """Per-(block, shift) weighted risk + the count of contributing incidents."""

    risk: dict[tuple[str, str], float]     # (blockcode, shift) -> weighted risk
    support: dict[tuple[str, str], float]  # (blockcode, shift) -> relevant count
    baseline: float                        # citywide median risk over active blocks
    risk_scale: float                      # risk at RISK_SCALE_PERCENTILE
    shifts: tuple[str, ...] = field(default=("Day", "Evening", "Night"))

    def lookup(self, blockcode: str, shift: str) -> tuple[float, float]:
        key = (str(blockcode), shift)
        return self.risk.get(key, 0.0), self.support.get(key, 0.0)


def build_crime_index(incidents: pd.DataFrame) -> CrimeRiskIndex:
    df = incidents.copy()
    df["w_rel"] = [
        relevance_weight(t, c)
        for t, c in zip(df["offensetype"], df.get("offensecode"))
    ]
    df = df[df["w_rel"] > 0].copy()
    df["shift"] = df["police_shift"].map(_normalize_shift)
    df = df[df["shift"].notna()]
    df["w_rec"] = df["year"].map(recency_weight)
    df["blockcode"] = df["blockcode"].astype(str)

    # Weighted risk contribution of each incident (before shift gating, which
    # depends on the *query* shift and is applied at score time).
    df["contrib"] = df["w_rel"] * df["w_rec"]

    risk: dict[tuple[str, str], float] = {}
    support: dict[tuple[str, str], float] = {}
    for (block, shift), grp in df.groupby(["blockcode", "shift"]):
        risk[(block, shift)] = float(grp["contrib"].sum())
        support[(block, shift)] = float(len(grp))

    # Baseline + scale computed over the in-shift risk of active blocks only.
    vals = np.array(list(risk.values())) if risk else np.array([0.0])
    baseline = float(np.median(vals))
    risk_scale = float(np.percentile(vals, RISK_SCALE_PERCENTILE))
    if risk_scale <= 0:
        risk_scale = baseline if baseline > 0 else 1.0

    return CrimeRiskIndex(risk=risk, support=support, baseline=baseline, risk_scale=risk_scale)


# ---------------------------------------------------------------------------
# Geocoding: lat/lng -> 2020 census block GEOID
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=4096)
def latlng_to_block(lat: float, lng: float) -> str | None:
    """Resolve a coordinate to its 15-digit 2020 census block GEOID."""
    resp = httpx.get(
        CENSUS_GEOCODER_URL,
        params={
            "x": lng,
            "y": lat,
            "benchmark": "Public_AR_Current",
            "vintage": "Census2020_Current",
            "layers": "Census Blocks",
            "format": "json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    blocks = resp.json().get("result", {}).get("geographies", {}).get("Census Blocks", [])
    return blocks[0]["GEOID"] if blocks else None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
@dataclass
class LayerScore:
    score: float
    reasons: list[str]


def score_crime(index: CrimeRiskIndex, blockcode: str | None, event_hour: int) -> LayerScore:
    """Crime-layer score for a census block, for a gathering at `event_hour` (0-23)."""
    if blockcode is None:
        return LayerScore(75.0, ["Could not resolve venue to a census block — neutral default."])

    event_shift = shift_for_hour(event_hour)
    block = str(blockcode)

    # Relevant risk in the matching shift (full weight) + other shifts (damped:
    # a daytime assault is mild evidence about the block even for an evening
    # event). n_total counts every contributing incident so the shrinkage guard
    # and the risk are consistent.
    r_match, n_match = index.lookup(block, event_shift)
    raw_risk = SHIFT_MATCH_WEIGHT * r_match
    n_total = n_match
    for shift in index.shifts:
        if shift == event_shift:
            continue
        r, n = index.lookup(block, shift)
        raw_risk += SHIFT_OFF_WEIGHT * r
        n_total += n

    # Anti-one-off guard 1: empirical-Bayes shrinkage toward the citywide
    # baseline. A block with 1 incident is pulled ~2/3 of the way to baseline.
    shrunk = (
        (n_total / (n_total + SHRINKAGE_K)) * raw_risk
        + (SHRINKAGE_K / (n_total + SHRINKAGE_K)) * index.baseline
    )

    # Anti-one-off guard 2: saturating, baseline-normalized transform.
    # score = 100 at zero risk, 50 at the p75 block, asymptotes toward 0.
    score = 100.0 * index.risk_scale / (shrunk + index.risk_scale)
    score = round(max(0.0, min(100.0, score)), 1)

    reasons = _reasons(index, event_shift, n_match, n_total, raw_risk)
    return LayerScore(score=score, reasons=reasons)


def _reasons(index, event_shift, n_match, n_total, raw_risk) -> list[str]:
    reasons: list[str] = []
    window = {"Day": "8am-4pm", "Evening": "4pm-12am", "Night": "12am-8am"}[event_shift]

    if n_total == 0:
        reasons.append(
            "No crowd-relevant incidents recorded on this block — scored at the "
            "neutral citywide baseline."
        )
        reasons.append(
            "Scored on this block only, time-gated to the event window, by incident "
            "type — never a neighborhood blanket label."
        )
        return reasons

    reasons.append(
        f"{int(n_match)} crowd-relevant incident(s) on this block during the "
        f"{event_shift.lower()} window ({window})"
        + (
            f"; {int(n_total - n_match)} more at other times (counted at reduced weight)."
            if n_total > n_match
            else "."
        )
    )
    if n_total < SHRINKAGE_K:
        reasons.append(
            "Too few incidents to be statistically meaningful — score pulled toward "
            "the citywide baseline rather than penalizing a one-off."
        )
    # Contextualize vs. the city using the same effective risk that drove the score.
    if raw_risk > index.risk_scale:
        reasons.append("Above the 75th-percentile Somerville block for relevant crime at this time.")
    elif raw_risk <= index.baseline:
        reasons.append("At or below the typical Somerville block for this time of day.")
    reasons.append(
        "Scored on this block only, time-gated to the event window, by incident "
        "type — never a neighborhood blanket label."
    )
    return reasons


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Loading Somerville crime incidents...")
    incidents = load_crime_incidents()
    print(f"  {len(incidents):,} rows")

    index = build_crime_index(incidents)
    print(f"  baseline risk (median active block): {index.baseline:.3f}")
    print(f"  risk scale (p{RISK_SCALE_PERCENTILE}): {index.risk_scale:.3f}")
    print(f"  active (block, shift) cells: {len(index.risk):,}")

    # Davis Square, 7pm watch party.
    lat, lng, hour = 42.3967, -71.1226, 19
    block = latlng_to_block(lat, lng)
    print(f"\nDavis Square ({lat}, {lng}) -> block {block}, {hour}:00")
    result = score_crime(index, block, hour)
    print(f"  Crime score: {result.score}")
    for r in result.reasons:
        print(f"   - {r}")
