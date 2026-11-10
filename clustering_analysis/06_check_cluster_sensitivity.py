"""Check the sensitivity of the three-cluster solution to high wind-rate values."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits


OUTPUTS = Path(__file__).resolve().parent / "outputs"
WIND = "high_wind_rate"
FEATURES = ["delay_rate", "median_delay_min_among_delayed", WIND, "low_visibility_rate"]


def compare(airports: pd.DataFrame) -> dict:
    scaled = StandardScaler().fit_transform(airports[FEATURES].to_numpy(dtype=float))
    model = KMeans(n_clusters=3, random_state=42, n_init=50)
    labels = model.fit_predict(scaled)
    counts = pd.crosstab(airports["cluster"].to_numpy(), labels)
    rows, cols = linear_sum_assignment(-counts.to_numpy())
    label_map = dict(zip(counts.columns[cols], counts.index[rows]))
    aligned = pd.Series(labels, index=airports.index).map(label_map)
    unchanged = aligned.eq(airports["cluster"])
    return {
        "compared_airports": len(airports),
        "unchanged_airports": int(unchanged.sum()),
        "changed_airports": int((~unchanged).sum()),
        "adjusted_rand_index": adjusted_rand_score(airports["cluster"], labels),
        "silhouette": silhouette_score(scaled, labels),
        "changed_airport_codes": ", ".join(airports.loc[~unchanged, "origin"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=OUTPUTS / "airport_cluster_assignments.csv")
    parser.add_argument("--output", type=Path, default=OUTPUTS / "airport_cluster_sensitivity.csv")
    args = parser.parse_args()

    airports = pd.read_csv(args.input).sort_values("origin").reset_index(drop=True)
    if airports["origin"].isna().any() or airports["origin"].duplicated().any():
        raise ValueError("Expected one row per nonmissing departure airport.")
    if len(airports) < 5 or set(airports["cluster"]) != {1, 2, 3} or not np.isfinite(airports[FEATURES]).all().all():
        raise ValueError("Expected a three-cluster assignment table with finite feature values.")

    top_index = airports[WIND].idxmax()
    top = airports.loc[top_index]
    cap = airports[WIND].quantile(0.95)
    capped = airports.assign(high_wind_rate=airports[WIND].clip(upper=cap))
    with threadpool_limits(limits=1):
        baseline = compare(airports)
        if baseline["changed_airports"]:
            raise ValueError("Refitting the original data did not reproduce the saved assignments.")
        result = pd.DataFrame([
            {"scenario": "original", "excluded_airport": "", "wind_cap": None, "capped_airports": 0,
             **baseline},
            {"scenario": "remove_highest_wind_airport", "excluded_airport": top["origin"],
             "wind_cap": None, "capped_airports": 0, **compare(airports.drop(index=top_index))},
            {"scenario": "cap_wind_rate_at_p95", "excluded_airport": "", "wind_cap": cap,
             "capped_airports": int(airports[WIND].gt(cap).sum()), **compare(capped)},
        ])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"Highest wind rate: {top['origin']} ({top[WIND]:.2%})")
    print(f"Wind rate 95th percentile: {cap:.2%}")
    summary = result[["scenario", "compared_airports", "unchanged_airports", "adjusted_rand_index", "silhouette"]]
    print(summary.to_string(index=False, float_format="{:.4f}".format))
    print(f"Saved: {args.output.resolve()}")


if __name__ == "__main__":
    main()
