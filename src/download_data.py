"""Downloads the hourly OPSD time series (version 2020-10-06) and keeps only
the German price, solar and wind columns from 2019 on."""

from pathlib import Path

import pandas as pd

URL = (
    "https://data.open-power-system-data.org/time_series/2020-10-06/"
    "time_series_60min_singleindex.csv"
)
COLUMNS = [
    "utc_timestamp",
    "DE_LU_price_day_ahead",
    "DE_solar_capacity",
    "DE_solar_generation_actual",
    "DE_solar_profile",
    "DE_wind_onshore_capacity",
    "DE_wind_onshore_generation_actual",
    "DE_wind_onshore_profile",
]
OUT = Path(__file__).resolve().parents[1] / "data" / "opsd_germany_hourly.csv"


def main() -> None:
    print(f"Downloading {URL} (about 120 MB, this can take a few minutes)...")
    header = pd.read_csv(URL, nrows=0).columns
    usecols = [c for c in COLUMNS if c in header]
    missing = sorted(set(COLUMNS) - set(usecols))
    if missing:
        print(f"Columns not found in the source and skipped: {missing}")
    df = pd.read_csv(URL, usecols=usecols, parse_dates=["utc_timestamp"])
    df = df[df["utc_timestamp"] >= "2019-01-01"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Saved {len(df):,} hourly rows to {OUT}")


if __name__ == "__main__":
    main()
