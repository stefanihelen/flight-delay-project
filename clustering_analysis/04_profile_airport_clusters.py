"""Fit the three-cluster airport model and export membership and group profiles."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits


OUTPUTS = Path(__file__).resolve().parent / "outputs"
FEATURES = [
    "delay_rate",
    "median_delay_min_among_delayed",
    "high_wind_rate",
    "low_visibility_rate",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=OUTPUTS / "airport_clustering_input.csv")
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS)
    args = parser.parse_args()

    airports = pd.read_csv(args.input).sort_values("origin").reset_index(drop=True)
    if airports["origin"].isna().any() or airports["origin"].duplicated().any():
        raise ValueError("Expected one row per nonmissing departure airport.")
    features = airports[FEATURES].to_numpy(dtype=float)
    if not np.isfinite(features).all() or len(features) < 4 or len(np.unique(features, axis=0)) < 3:
        raise ValueError("Expected at least four airports with finite features and three distinct profiles.")

    scaled = StandardScaler().fit_transform(features)
    model = KMeans(n_clusters=3, n_init=50, random_state=42)
    with threadpool_limits(limits=1):
        labels = model.fit_predict(scaled)
        score = silhouette_score(scaled, labels)

    # Number the groups from lowest to highest mean airport delay rate.
    order = np.argsort(model.cluster_centers_[:, FEATURES.index("delay_rate")], kind="stable")
    cluster_number = {label: number for number, label in enumerate(order, start=1)}
    airports["cluster"] = pd.Series(labels).map(cluster_number)
    airports["distance_to_center"] = np.linalg.norm(scaled - model.cluster_centers_[labels], axis=1)

    groups = airports.groupby("cluster")
    profiles = groups.agg(
        airports=("origin", "size"),
        valid_arrivals=("valid_arrivals", "sum"),
        mean_delay_rate=("delay_rate", "mean"),
        mean_median_delay_min=("median_delay_min_among_delayed", "mean"),
        mean_severe_delay_rate=("severe_delay_rate", "mean"),
        mean_high_wind_rate=("high_wind_rate", "mean"),
        mean_low_visibility_rate=("low_visibility_rate", "mean"),
    )
    nearest = airports.sort_values(["distance_to_center", "origin"]).groupby("cluster").head(3)
    profiles["representative_airports"] = nearest.groupby("cluster")["origin"].agg(", ".join)
    profiles = profiles.reset_index()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    assignments_path = args.output_dir / "airport_cluster_assignments.csv"
    profiles_path = args.output_dir / "airport_cluster_profiles.csv"
    airports.sort_values(["cluster", "origin"]).to_csv(assignments_path, index=False, encoding="utf-8-sig")
    profiles.to_csv(profiles_path, index=False, encoding="utf-8-sig")

    print(f"K=3, silhouette={score:.4f}")
    print(profiles.to_string(index=False, formatters={
        "mean_delay_rate": "{:.2%}".format,
        "mean_median_delay_min": "{:.2f}".format,
        "mean_severe_delay_rate": "{:.2%}".format,
        "mean_high_wind_rate": "{:.2%}".format,
        "mean_low_visibility_rate": "{:.2%}".format,
    }))
    print(f"Assignments: {assignments_path.resolve()}")
    print(f"Profiles: {profiles_path.resolve()}")


if __name__ == "__main__":
    main()
