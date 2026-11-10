"""Summarize 2024 flight delays and matched weather by departure airport."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from pyarrow.parquet import ParquetFile


PROJECT = Path(__file__).resolve().parent
BATCH_SIZE = 250_000
USABLE_QUALITY = {"0", "1", "4", "5", "C", "A"}
COLUMNS = [
    "origin", "cancelled", "diverted", "arr_delay_min", "arr_del15",
    "weather_match_status", "weather_gap_minutes",
    "wind_speed_kts", "wind_speed_q", "vis_m", "vis_q",
]


def summarize_airports(path: Path) -> pd.DataFrame:
    parquet = ParquetFile(path)
    batch_counts = []
    delayed_flights = []

    for batch in parquet.iter_batches(batch_size=BATCH_SIZE, columns=COLUMNS):
        flights = batch.to_pandas()
        if flights["origin"].isna().any():
            raise ValueError("Missing departure airport code in source data.")

        delay = flights["arr_delay_min"]
        valid = flights["cancelled"].eq(0) & flights["diverted"].eq(0) & np.isfinite(delay)
        delayed = valid & delay.ge(15)
        severe = valid & delay.ge(60)
        if not flights.loc[valid, "arr_del15"].eq(delayed.loc[valid].astype(int)).all():
            raise ValueError("Source arr_del15 disagrees with the 15-minute delay rule.")

        matched = (
            valid
            & flights["weather_match_status"].eq("matched")
            & flights["weather_gap_minutes"].between(0, 90)
        )
        wind = flights["wind_speed_kts"]
        visibility = flights["vis_m"]
        wind_usable = matched & np.isfinite(wind) & wind.ge(0) & flights["wind_speed_q"].isin(USABLE_QUALITY)
        visibility_usable = (
            matched & np.isfinite(visibility) & visibility.ge(0) & flights["vis_q"].isin(USABLE_QUALITY)
        )

        flags = pd.DataFrame({
            "origin": flights["origin"],
            "all_flights": 1,
            "valid_arrivals": valid,
            "delayed_arrivals": delayed,
            "severe_delays": severe,
            "weather_matched": matched,
            "usable_wind": wind_usable,
            "high_wind": wind_usable & wind.ge(20),
            "usable_visibility": visibility_usable,
            "low_visibility": visibility_usable & visibility.lt(5_000),
        })
        batch_counts.append(flags.groupby("origin", observed=True).sum())
        delayed_flights.append(flights.loc[delayed, ["origin", "arr_delay_min"]])

    airports = pd.concat(batch_counts).groupby(level="origin", observed=True).sum()
    delayed_rows = pd.concat(delayed_flights, ignore_index=True)
    medians = delayed_rows.groupby("origin", observed=True)["arr_delay_min"].median()
    airports["median_delay_min_among_delayed"] = medians

    rate_columns = {
        "delay_rate": ("delayed_arrivals", "valid_arrivals"),
        "severe_delay_rate": ("severe_delays", "valid_arrivals"),
        "weather_match_rate": ("weather_matched", "valid_arrivals"),
        "wind_coverage_rate": ("usable_wind", "valid_arrivals"),
        "visibility_coverage_rate": ("usable_visibility", "valid_arrivals"),
        "high_wind_rate": ("high_wind", "usable_wind"),
        "low_visibility_rate": ("low_visibility", "usable_visibility"),
    }
    for name, (numerator, denominator) in rate_columns.items():
        base = airports[denominator]
        airports[name] = airports[numerator].div(base.where(base.gt(0)))

    if airports["all_flights"].sum() != parquet.metadata.num_rows:
        raise ValueError("Airport counts do not sum to the number of source rows.")
    return airports.sort_index().reset_index()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT.parent / "data_fusion" / "data" / "integrated" / "flights_weather_2024.parquet",
    )
    parser.add_argument("--output", type=Path, default=PROJECT / "outputs" / "airport_summary.csv")
    args = parser.parse_args()

    airports = summarize_airports(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    airports.to_csv(args.output, index=False, encoding="utf-8-sig")

    print(f"Airports: {len(airports):,}")
    for column in ("all_flights", "valid_arrivals", "delayed_arrivals", "severe_delays"):
        print(f"{column}: {airports[column].sum():,}")
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()
