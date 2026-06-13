"""
Ingest the City of Somerville crime dataset into a local cache.

Source: https://data.somervillema.gov/Public-Safety/Police-Data-Crime-Reports/aghs-hqvg
~22.6k rows, refreshed daily with a ~1-month delay. No coordinates — only a
15-digit census block GEOID (`blockcode`) and a coarse `police_shift`.

Run:  python -m backend.data.ingest_crime
"""

from __future__ import annotations

import pathlib

import httpx
import pandas as pd

SOCRATA_URL = "https://data.somervillema.gov/resource/aghs-hqvg.json"
CACHE_DIR = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache"
COLUMNS = "incnum,blockcode,ward,offense,offensecode,offensetype,category,police_shift,year,day_and_month"


def fetch_all() -> pd.DataFrame:
    resp = httpx.get(
        SOCRATA_URL,
        params={"$select": COLUMNS, "$limit": 200000, "$order": "incnum"},
        timeout=120.0,
    )
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())
    df["blockcode"] = df["blockcode"].astype(str)
    return df


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching from {SOCRATA_URL} ...")
    df = fetch_all()
    print(f"  {len(df):,} rows, {df['blockcode'].nunique():,} distinct blocks")

    out = CACHE_DIR / "crime.parquet"
    try:
        df.to_parquet(out, index=False)
    except Exception:  # pyarrow not installed -> fall back to CSV
        out = CACHE_DIR / "crime.csv"
        df.to_csv(out, index=False)
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
