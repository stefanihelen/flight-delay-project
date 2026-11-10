"""Select departure airports for clustering from the annual summary table."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


OUTPUTS = Path(__file__).resolve().parent / "outputs"
FEATURES = [
    "delay_rate",
    "median_delay_min_among_delayed",
    "high_wind_rate",
    "low_visibility_rate",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=OUTPUTS / "airport_summary.csv")
    parser.add_argument("--output", type=Path, default=OUTPUTS / "airport_clustering_input.csv")
    parser.add_argument("--min-arrivals", type=int, default=1000)
    parser.add_argument("--min-weather-coverage", type=float, default=0.80)
    args = parser.parse_args()
    if args.min_arrivals < 1 or not 0 <= args.min_weather_coverage <= 1:
        parser.error("Use a positive arrival threshold and a weather coverage threshold between 0 and 1.")

    airports = pd.read_csv(args.input)
    if airports["origin"].isna().any() or airports["origin"].duplicated().any():
        raise ValueError("Expected one row per nonmissing departure airport.")

    enough_arrivals = airports["valid_arrivals"].ge(args.min_arrivals)
    enough_weather = (
        airports["wind_coverage_rate"].ge(args.min_weather_coverage)
        & airports["visibility_coverage_rate"].ge(args.min_weather_coverage)
    )
    selected = airports.loc[enough_arrivals & enough_weather].sort_values("origin")
    if selected.empty or not np.isfinite(selected[FEATURES].to_numpy()).all():
        raise ValueError("The selected airports must have finite values for all four clustering features.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(args.output, index=False, encoding="utf-8-sig")

    total_arrivals = airports["valid_arrivals"].sum()
    selected_arrivals = selected["valid_arrivals"].sum()
    weather_excluded = airports.loc[enough_arrivals & ~enough_weather, "origin"].sort_values()
    print(f"Input airports: {len(airports):,}")
    print(f"Excluded for low flight count: {(~enough_arrivals).sum():,}")
    print(f"Excluded for low weather coverage after count screen: {len(weather_excluded):,}")
    if not weather_excluded.empty:
        print(f"Low-weather-coverage airports: {', '.join(weather_excluded)}")
    print(f"Eligible airports: {len(selected):,}")
    print(f"Eligible valid arrivals: {selected_arrivals:,} ({selected_arrivals / total_arrivals:.2%})")
    print(f"Clustering features: {', '.join(FEATURES)}")
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()
