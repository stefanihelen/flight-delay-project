"""Compare candidate K-means cluster counts for the screened airports."""

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
CANDIDATE_K = range(2, 9)
RANDOM_SEED = 42
N_INIT = 50


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=OUTPUTS / "airport_clustering_input.csv")
    parser.add_argument("--output", type=Path, default=OUTPUTS / "kmeans_evaluation.csv")
    args = parser.parse_args()

    airports = pd.read_csv(args.input).sort_values("origin")
    if airports["origin"].isna().any() or airports["origin"].duplicated().any():
        raise ValueError("Expected one row per nonmissing departure airport.")
    features = airports[FEATURES].to_numpy(dtype=float)
    if not np.isfinite(features).all():
        raise ValueError("All four clustering features must be finite.")
    if len(features) <= max(CANDIDATE_K) or len(np.unique(features, axis=0)) < max(CANDIDATE_K):
        raise ValueError("The candidate range requires more than eight airports and at least eight distinct profiles.")

    scaled = StandardScaler().fit_transform(features)
    comparison = []
    with threadpool_limits(limits=1):
        for k in CANDIDATE_K:
            model = KMeans(n_clusters=k, n_init=N_INIT, random_state=RANDOM_SEED)
            labels = model.fit_predict(scaled)
            sizes = np.sort(np.bincount(labels))
            comparison.append({
                "k": k,
                "silhouette": silhouette_score(scaled, labels),
                "inertia": model.inertia_,
                "smallest_cluster": sizes[0],
                "cluster_sizes": ", ".join(map(str, sizes)),
            })

    result = pd.DataFrame(comparison)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"Airports: {len(airports):,}")
    print(f"Features: {', '.join(FEATURES)}")
    print(f"Random seed: {RANDOM_SEED}; initializations per K: {N_INIT}")
    print(result.to_string(index=False, formatters={"silhouette": "{:.4f}".format, "inertia": "{:.2f}".format}))
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()
