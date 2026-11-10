"""Stream verified member2 flight-weather data into a compact regression CSV.

This script neither executes supplied archive code nor imputes missing outcomes.
Main outcome analysis must filter y_delay >= 0; cancellation/diversion rows are
retained for the separately defined disruption sensitivity analysis.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow
import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parents[1]
INPUT = BASE / "work/member2/data/integrated/flights_weather_2024.parquet"
OUTPUT = BASE / "work/model_data.csv"
TABLES = BASE / "outputs/member4_regression/tables"
EXPECTED_SHA256 = "7eb3dc4b1eceaf994207717f3460f6df7d0a519c21b3f4ecb2f9654d592f610b"
BATCH_SIZE = 250_000
WEATHER = ["temp_c", "wind_speed_kts", "vis_m", "precip_mm"]
QUALITY = ["temp_q", "wind_speed_q", "vis_q", "precip_q"]
USABLE_QUALITY = {"0", "1", "4", "5", "C", "A"}
STRICT_QUALITY = {"1", "5"}
COLUMNS = [
    "flight_id", "flight_date", "sched_dep_local", "dep_utc", "origin",
    "dest", "reporting_airline", "station_id", "distance_miles",
    "arr_delay_min", "arr_del15", "cancelled", "diverted",
    "weather_match_status", "weather_obs_utc", "weather_gap_minutes",
    "weather_match_within_60", "precip_period_h", *WEATHER, *QUALITY,
]
STAGES = [
    "all_input", "matched_weather_0_to_90_min", "four_weather_values_finite",
    "four_weather_quality_usable", "precipitation_period_one_hour",
    "nonnegative_wind_visibility_precipitation", "valid_controls_and_distance",
]


def diagnose_monthly_weather(input_path: Path, tables_path: Path) -> list[dict]:
    """Locate seasonal sample attrition; counts can overlap across missing fields."""
    totals = defaultdict(Counter)
    cols = ["flight_date", "weather_match_status", "weather_gap_minutes", "precip_period_h", *WEATHER, *QUALITY]
    for batch in pq.ParquetFile(input_path).iter_batches(batch_size=BATCH_SIZE, columns=cols):
        d = batch.to_pandas()
        month = pd.to_datetime(d.flight_date).dt.month
        matched = d.weather_match_status.eq("matched") & d.weather_gap_minutes.between(0, 90)
        finite = pd.Series(True, index=d.index)
        for col in WEATHER:
            finite &= np.isfinite(d[col])
        quality = pd.Series(True, index=d.index)
        for col in QUALITY:
            quality &= d[col].isin(USABLE_QUALITY)
        masks = {
            "input_n": pd.Series(True, index=d.index),
            "matched_n": matched,
            "complete_weather_matched_n": matched & finite,
            "excluded_quality_among_complete_n": matched & finite & ~quality,
            "non_one_hour_precip_remaining_n": matched & finite & quality & ~d.precip_period_h.eq(1),
        }
        for col in WEATHER:
            masks[f"{col}_nonfinite_matched_n"] = matched & ~np.isfinite(d[col])
        for label, mask in masks.items():
            for m, n in month[mask].value_counts().items():
                totals[int(m)][label] += int(n)
    labels = list(masks)
    rows = [{"month": m, **{label: counts[label] for label in labels}} for m, counts in sorted(totals.items())]
    pd.DataFrame(rows).to_csv(tables_path / "monthly_weather_quality.csv", index=False, encoding="utf-8-sig")
    return rows


def main() -> None:
    global INPUT, OUTPUT, TABLES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT, help="Integrated flight-weather Parquet")
    parser.add_argument("--work", type=Path, default=BASE / "work", help="Directory for model_data.csv")
    parser.add_argument("--out", type=Path, default=BASE / "outputs/member4_regression", help="Deliverable root (tables and code created below it)")
    args = parser.parse_args()
    INPUT = args.input.resolve()
    OUTPUT = args.work.resolve() / "model_data.csv"
    TABLES = args.out.resolve() / "tables"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone().isoformat()
    with INPUT.open("rb") as handle:
        source_sha = hashlib.file_digest(handle, "sha256").hexdigest()
    if source_sha != EXPECTED_SHA256:
        raise RuntimeError("Input SHA256 differs from the supplied member3 input checksum")
    print(f"Input SHA256 verified: {source_sha}", flush=True)
    source = pq.ParquetFile(INPUT)
    flow = {stage: Counter() for stage in STAGES}
    checks = Counter()
    quality_counts = defaultdict(Counter)
    numeric_present_q9 = Counter()
    missing_counts = Counter()
    nonfinite_counts = Counter()
    control_missing = Counter()
    match_status = Counter()
    periods = Counter()
    ranges = defaultdict(lambda: [float("inf"), float("-inf")])
    by_month = defaultdict(Counter)
    selected_categories = defaultdict(Counter)
    hashes: list[np.ndarray] = []
    selected_origins: set[str] = set()
    selected_destinations: set[str] = set()
    selected_airlines: set[str] = set()
    selected_stations: set[str] = set()
    selected_routes: set[str] = set()
    total_written = 0
    max_gap_difference = 0.0

    def update_ranges(scope: str, frame: pd.DataFrame) -> None:
        for col in [*WEATHER, "distance_miles", "arr_delay_min", "weather_gap_minutes"]:
            values = frame[col].to_numpy(dtype=float)
            valid = values[np.isfinite(values)]
            if valid.size:
                key = f"{scope}:{col}"
                ranges[key][0] = min(ranges[key][0], float(valid.min()))
                ranges[key][1] = max(ranges[key][1], float(valid.max()))

    def record_stage(name: str, mask: pd.Series, frame: pd.DataFrame,
                     valid: pd.Series, delayed: pd.Series, severe: pd.Series) -> None:
        out = flow[name]
        out["all_flights"] += int(mask.sum())
        out["valid_arrivals"] += int((mask & valid).sum())
        out["delayed_ge15"] += int((mask & delayed).sum())
        out["severe_ge60"] += int((mask & severe).sum())
        out["cancelled"] += int((mask & frame.cancelled.eq(1)).sum())
        out["diverted"] += int((mask & frame.diverted.eq(1)).sum())

    with OUTPUT.open("w", encoding="utf-8", newline="") as csv_handle:
        for batch_number, batch in enumerate(source.iter_batches(batch_size=BATCH_SIZE, columns=COLUMNS), 1):
            d = batch.to_pandas()
            n = len(d)
            d["flight_date"] = pd.to_datetime(d.flight_date)
            for col in ["sched_dep_local", "dep_utc", "weather_obs_utc"]:
                d[col] = pd.to_datetime(d[col])
            hashes.append(pd.util.hash_pandas_object(d.flight_id, index=False).to_numpy(dtype=np.uint64))
            checks["flight_id_missing"] += int(d.flight_id.isna().sum())
            checks["flight_date_missing_or_not_2024"] += int((~d.flight_date.dt.year.eq(2024)).sum())
            checks["invalid_cancelled_code"] += int((~d.cancelled.isin([0, 1])).sum())
            checks["invalid_diverted_code"] += int((~d.diverted.isin([0, 1])).sum())
            checks["cancelled_and_diverted_both_one"] += int((d.cancelled.eq(1) & d.diverted.eq(1)).sum())
            checks["arr_delay_infinite"] += int(np.isinf(d.arr_delay_min.to_numpy(dtype=float)).sum())
            valid = (d.cancelled.eq(0) & d.diverted.eq(0)
                     & d.arr_del15.isin([0, 1]) & np.isfinite(d.arr_delay_min))
            delayed = valid & d.arr_delay_min.ge(15)
            severe = valid & d.arr_delay_min.ge(60)
            checks["valid_arrival_label_inconsistency"] += int((valid & d.arr_del15.ne(d.arr_delay_min.ge(15))).sum())
            matched = d.weather_match_status.eq("matched")
            finite_gap = pd.Series(np.isfinite(d.weather_gap_minutes), index=d.index)
            good_gap = finite_gap & d.weather_gap_minutes.between(0, 90)
            checks["matched_invalid_gap"] += int((matched & ~good_gap).sum())
            dt_gap = (d.dep_utc - d.weather_obs_utc).dt.total_seconds() / 60
            checks["matched_timestamp_missing"] += int((matched & (d.dep_utc.isna() | d.weather_obs_utc.isna())).sum())
            checks["matched_future_weather"] += int((matched & dt_gap.lt(0)).sum())
            diff = (dt_gap - d.weather_gap_minutes).abs()
            checks["matched_gap_timestamp_disagreement_gt_0_001min"] += int((matched & diff.gt(0.001)).sum())
            if matched.any():
                max_gap_difference = max(max_gap_difference, float(diff[matched].max()))
            expected60 = matched & good_gap & d.weather_gap_minutes.le(60)
            checks["within60_flag_disagreement"] += int(d.weather_match_within_60.ne(expected60).sum())
            match_status.update(d.weather_match_status.astype("string").fillna("<NA>").value_counts().to_dict())
            periods.update(d.precip_period_h.astype("string").fillna("<NA>").value_counts().to_dict())
            for col in WEATHER:
                missing_counts[col] += int(d[col].isna().sum())
                nonfinite_counts[col] += int((~np.isfinite(d[col])).sum())
            for col in ["flight_date", "sched_dep_local", "origin", "dest", "reporting_airline", "station_id", "distance_miles"]:
                control_missing[col] += int(d[col].isna().sum())
            for col in QUALITY:
                quality_counts[("all_input", col)].update(d[col].astype("string").fillna("<NA>").value_counts().to_dict())
                quality_counts[("matched", col)].update(d.loc[matched, col].astype("string").fillna("<NA>").value_counts().to_dict())
            for value_col, quality_col in zip(WEATHER, QUALITY):
                numeric_present_q9[quality_col] += int((np.isfinite(d[value_col]) & d[quality_col].eq("9")).sum())
            update_ranges("all_input", d)
            month = d.flight_date.dt.month
            for m, count in month.value_counts().items():
                by_month[int(m)]["all_input"] += int(count)
            for m, count in month[valid].value_counts().items():
                by_month[int(m)]["valid_arrivals_input"] += int(count)
            mask = pd.Series(True, index=d.index)
            record_stage(STAGES[0], mask, d, valid, delayed, severe)
            mask &= matched & good_gap
            record_stage(STAGES[1], mask, d, valid, delayed, severe)
            for col in WEATHER:
                mask &= np.isfinite(d[col])
            record_stage(STAGES[2], mask, d, valid, delayed, severe)
            for col in QUALITY:
                mask &= d[col].isin(USABLE_QUALITY)
            record_stage(STAGES[3], mask, d, valid, delayed, severe)
            mask &= d.precip_period_h.eq(1)
            record_stage(STAGES[4], mask, d, valid, delayed, severe)
            mask &= d.wind_speed_kts.ge(0) & d.vis_m.ge(0) & d.precip_mm.ge(0)
            record_stage(STAGES[5], mask, d, valid, delayed, severe)
            controls_ok = (d.flight_date.dt.year.eq(2024) & d.sched_dep_local.notna()
                           & d.sched_dep_local.dt.hour.between(0, 23)
                           & np.isfinite(d.distance_miles) & d.distance_miles.gt(0))
            for col in ["origin", "dest", "reporting_airline", "station_id"]:
                controls_ok &= d[col].notna() & d[col].astype("string").str.strip().ne("").fillna(False)
            mask &= controls_ok
            record_stage(STAGES[6], mask, d, valid, delayed, severe)
            s = d.loc[mask].copy()
            update_ranges("selected", s)
            main = valid.loc[mask]
            for m, count in month[mask].value_counts().items():
                by_month[int(m)]["selected_all_outcomes"] += int(count)
            for m, count in month[mask & valid].value_counts().items():
                by_month[int(m)]["selected_main_arrivals"] += int(count)
            for m, count in month[mask & delayed].value_counts().items():
                by_month[int(m)]["selected_main_delayed"] += int(count)
            for col in QUALITY:
                quality_counts[("selected", col)].update(s[col].astype("string").fillna("<NA>").value_counts().to_dict())
            strict = pd.Series(True, index=s.index)
            for col in QUALITY:
                strict &= s[col].isin(STRICT_QUALITY)
            y_delay = np.where(main, s.arr_delay_min.ge(15).astype(np.int8), -1).astype(np.int8)
            y_severe = np.where(main, s.arr_delay_min.ge(60).astype(np.int8), -1).astype(np.int8)
            y_disrupt = np.where(s.cancelled.eq(1) | s.diverted.eq(1) | (y_delay == 1), 1,
                                 np.where(y_delay == 0, 0, -1)).astype(np.int8)
            wind = np.select([s.wind_speed_kts.lt(5), s.wind_speed_kts.lt(10), s.wind_speed_kts.lt(20)], [0, 1, 2], default=3).astype(np.int8)
            vis = np.select([s.vis_m.ge(10000), s.vis_m.ge(5000), s.vis_m.ge(1000)], [0, 1, 2], default=3).astype(np.int8)
            origin = s.origin.astype("string")
            dest = s.dest.astype("string")
            airline = s.reporting_airline.astype("string")
            station = s.station_id.astype("string")
            route = origin + "_" + dest
            temp10 = (s.temp_c.astype(float) - 15.0) / 10.0
            out = pd.DataFrame({
                "date_id": (s.flight_date - pd.Timestamp("2024-01-01")).dt.days.astype(np.int16),
                "month": s.flight_date.dt.month.astype(np.int8),
                "weekday": (s.flight_date.dt.dayofweek + 1).astype(np.int8),
                "hour": s.sched_dep_local.dt.hour.astype(np.int8),
                "origin": origin, "dest": dest, "airline": airline,
                "station": station, "route": route,
                "distance_log": np.log(s.distance_miles / 500.0),
                "temp10": temp10, "temp10sq": temp10 ** 2,
                "wind": wind, "vis": vis,
                "rain": s.precip_mm.gt(0).astype(np.int8),
                "strict_q": strict.astype(np.int8),
                "within60": s.weather_gap_minutes.le(60).astype(np.int8),
                "y_delay": y_delay, "y_severe": y_severe, "y_disrupt": y_disrupt,
            })
            if out.isna().any().any():
                raise RuntimeError("Missing value reached compact model frame")
            out.to_csv(csv_handle, index=False, header=(total_written == 0), float_format="%.8g")
            total_written += len(out)
            selected_origins.update(origin.unique())
            selected_destinations.update(dest.unique())
            selected_airlines.update(airline.unique())
            selected_stations.update(station.unique())
            selected_routes.update(route.unique())
            for col in ["wind", "vis", "rain", "strict_q", "within60", "y_delay", "y_severe", "y_disrupt"]:
                selected_categories[col].update(out[col].value_counts().to_dict())
            print(f"Batch {batch_number}: read {flow['all_input']['all_flights']:,}; wrote {total_written:,}; main {flow[STAGES[-1]]['valid_arrivals']:,}", flush=True)

    all_hashes = np.concatenate(hashes)
    hashes.clear()
    unique_hashes = np.unique(all_hashes)
    duplicate_hash_rows = int(all_hashes.size - unique_hashes.size)
    checks["duplicate_flight_id_hash_rows"] = duplicate_hash_rows
    if duplicate_hash_rows:
        # A repeated hash might be a collision; fail pending exact ID inspection.
        raise RuntimeError(f"Repeated flight_id hashes ({duplicate_hash_rows}); inspect exact strings before modeling")
    if checks["flight_id_missing"]:
        raise RuntimeError("flight_id missing; uniqueness check cannot be certified")
    fatal_keys = ["flight_date_missing_or_not_2024", "invalid_cancelled_code", "invalid_diverted_code",
                  "valid_arrival_label_inconsistency", "matched_invalid_gap", "matched_timestamp_missing",
                  "matched_future_weather", "matched_gap_timestamp_disagreement_gt_0_001min",
                  "within60_flag_disagreement"]
    if any(checks[key] for key in fatal_keys):
        raise RuntimeError(f"Data validation failed: {dict(checks)}")
    if source.metadata.num_rows != flow["all_input"]["all_flights"]:
        raise RuntimeError("Streamed count differs from Parquet metadata")
    flow_rows = []
    previous_all = previous_main = None
    for stage in STAGES:
        values = dict(flow[stage])
        values["removed_all_from_previous"] = 0 if previous_all is None else previous_all - values["all_flights"]
        values["removed_valid_arrivals_from_previous"] = 0 if previous_main is None else previous_main - values["valid_arrivals"]
        previous_all, previous_main = values["all_flights"], values["valid_arrivals"]
        flow_rows.append({"stage": stage, **values})
    pd.DataFrame(flow_rows).to_csv(TABLES / "sample_flow.csv", index=False, encoding="utf-8-sig")
    qrows = [{"scope": scope, "field": field, "code": code, "n": int(n)}
             for (scope, field), counts in quality_counts.items()
             for code, n in sorted(counts.items())]
    pd.DataFrame(qrows).to_csv(TABLES / "quality_counts.csv", index=False, encoding="utf-8-sig")
    monthly = [{"month": month, **dict(counts)} for month, counts in sorted(by_month.items())]
    pd.DataFrame(monthly).to_csv(TABLES / "sample_by_month.csv", index=False, encoding="utf-8-sig")
    category_counts_json = {col: {str(key): int(val) for key, val in sorted(counts.items())}
                            for col, counts in selected_categories.items()}
    monthly_weather_diagnostics = diagnose_monthly_weather(INPUT, TABLES)
    audit = {
        "status": "passed", "started_at": started, "completed_at": datetime.now().astimezone().isoformat(),
        "input_path": str(INPUT), "input_sha256": source_sha, "expected_sha256_match": True,
        "input_rows": source.metadata.num_rows, "input_columns": len(source.schema_arrow),
        "batch_size": BATCH_SIZE, "output_path": str(OUTPUT), "output_rows": total_written,
        "output_columns": list(out.columns), "main_valid_arrivals": flow[STAGES[-1]]["valid_arrivals"],
        "checks": dict(checks), "maximum_gap_difference_minutes": max_gap_difference,
        "flight_id_uniqueness": {
            "method": "pandas.util.hash_pandas_object(index=False), deterministic uint64 hashes streamed then numpy.unique",
            "hashed_ids": int(all_hashes.size), "unique_hashes": int(unique_hashes.size),
            "duplicate_hash_rows": duplicate_hash_rows,
            "interpretation": "No missing IDs and no equal hashes; identical IDs would have equal deterministic hashes, so no identical flight_id values were found. Repeated hashes would require exact-string resolution.",
            "hash_collisions_observed": False,
        },
        "sample_flow": flow_rows, "monthly_sample_counts": monthly,
        "monthly_weather_quality_diagnostics": monthly_weather_diagnostics,
        "weather_missing_all_input": dict(missing_counts), "weather_nonfinite_all_input": dict(nonfinite_counts),
        "control_missing_all_input": dict(control_missing), "weather_match_status_all_input": dict(match_status),
        "precipitation_period_counts_all_input": dict(periods),
        "variable_ranges": {key: {"min": vals[0], "max": vals[1]} for key, vals in sorted(ranges.items())},
        "selected_category_counts": category_counts_json,
        "selected_distinct_counts": {"origin": len(selected_origins), "dest": len(selected_destinations),
                                     "airline": len(selected_airlines), "station": len(selected_stations), "route": len(selected_routes)},
        "quality_codes_usable": sorted(USABLE_QUALITY), "quality_codes_strict": sorted(STRICT_QUALITY),
        "numeric_present_quality_code9_all_input": dict(numeric_present_q9),
        "quality_filter_interpretation": "The main accepted set 0,1,4,5,A,C is prespecified and conservative. Other codes are outside this accepted set, not necessarily bad or missing. NOAA ISD code 9 means passed gross limits if the element is present.",
        "definitions": {
            "y_delay": "1 if valid arrival arr_delay_min >=15, 0 otherwise valid arrival, -1 otherwise",
            "y_severe": "1 if valid arrival arr_delay_min >=60, 0 otherwise valid arrival, -1 otherwise",
            "y_disrupt": "1 if cancelled=1 or diverted=1 or y_delay=1; 0 if y_delay=0; -1 otherwise",
            "valid_arrival": "cancelled=0 and diverted=0 and arr_del15 in {0,1} and finite arrival delay",
            "date_id": "Days since 2024-01-01 from flight_date; origin-local operating date",
            "wind": "0:<5; 1:[5,10); 2:[10,20); 3:>=20 knots",
            "vis": "0:>=10000; 1:[5000,10000); 2:[1000,5000); 3:<1000 meters",
            "rain": "1 if precipitation_mm>0; all retained observations have precipitation_period_h=1",
            "distance_log": "ln(distance_miles / 500)", "temp10": "(temperature_C - 15)/10",
            "temp10sq": "temp10 squared", "within60": "weather_gap_minutes<=60",
        },
        "limitations": [
            "All four weather variables must be finite and have usable codes; this is a complete-weather-record analysis, not an imputed full-population model.",
            "Positive precipitation is not identified as liquid rain versus snow; the compact name rain means any reported precipitation.",
            "Extreme but finite temperature/visibility/delay values are retained; no arbitrary winsorization or unverified corrections were applied.",
            "Unique flight_id verifies the provided identifiers, not the correctness of upstream entity resolution.",
            "Checks verify the provided timestamps and differences, not the original airport-timezone conversion or source weather-station mapping.",
        ],
        "software": {"pandas": pd.__version__, "numpy": np.__version__, "pyarrow": pyarrow.__version__},
    }
    (TABLES / "data_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    code_dir = args.out.resolve() / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    delivered_script = code_dir / "prepare_regression.py"
    if delivered_script.resolve() != Path(__file__).resolve():
        shutil.copyfile(__file__, delivered_script)
    print(json.dumps({"status": "passed", "rows": total_written, "main": flow[STAGES[-1]]["valid_arrivals"],
                      "output": str(OUTPUT), "audit": str(TABLES / "data_audit.json"), "checks": dict(checks)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
