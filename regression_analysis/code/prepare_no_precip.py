"""Create an expanded cohort for regression WITHOUT any precipitation terms.

The rain column is a constant-zero compatibility placeholder and MUST NOT be
used as an explanatory variable in expanded-cohort models. Other fields match
prepare_regression.py. Source identity and the main cohort are cross-checked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parents[1]
EXPECTED_SHA256 = "7eb3dc4b1eceaf994207717f3460f6df7d0a519c21b3f4ecb2f9654d592f610b"
ACCEPTED = {"0", "1", "4", "5", "C", "A"}
STRICT = {"1", "5"}
WEATHER = ["temp_c", "wind_speed_kts", "vis_m"]
QUALITY = ["temp_q", "wind_speed_q", "vis_q"]
STAGES = ["all_input", "matched_weather_0_to_90_min", "three_weather_values_finite",
          "three_weather_quality_usable", "nonnegative_wind_visibility", "valid_controls_and_distance"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASE / "work/member2/data/integrated/flights_weather_2024.parquet")
    parser.add_argument("--work", type=Path, default=BASE / "work")
    parser.add_argument("--out", type=Path, default=BASE / "outputs/member4_regression")
    args = parser.parse_args()
    source_path = args.input.resolve()
    csv_path = args.work.resolve() / "model_data_no_precip.csv"
    table_path = args.out.resolve() / "tables"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    table_path.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone().isoformat()
    with source_path.open("rb") as handle:
        source_sha = hashlib.file_digest(handle, "sha256").hexdigest()
    if source_sha != EXPECTED_SHA256:
        raise RuntimeError("Source hash mismatch")
    source = pq.ParquetFile(source_path)
    cols = ["flight_date", "sched_dep_local", "origin", "dest", "reporting_airline", "station_id",
            "distance_miles", "arr_delay_min", "arr_del15", "cancelled", "diverted", "weather_match_status",
            "weather_gap_minutes", "precip_mm", "precip_q", "precip_period_h", *WEATHER, *QUALITY]
    flow = {stage: Counter() for stage in STAGES}
    monthly = defaultdict(Counter)
    categories = defaultdict(Counter)
    original_cohort_main = original_cohort_all = 0
    written = 0
    header_written = False

    def record(stage: str, mask: pd.Series, valid: pd.Series, delayed: pd.Series) -> None:
        flow[stage]["all_flights"] += int(mask.sum())
        flow[stage]["valid_arrivals"] += int((mask & valid).sum())
        flow[stage]["delayed_ge15"] += int((mask & delayed).sum())

    def month_count(month: pd.Series, mask: pd.Series, label: str) -> None:
        for m, n in month[mask].value_counts().items():
            monthly[int(m)][label] += int(n)

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        for batch_n, batch in enumerate(source.iter_batches(batch_size=250_000, columns=cols), 1):
            d = batch.to_pandas()
            d["flight_date"] = pd.to_datetime(d.flight_date)
            d["sched_dep_local"] = pd.to_datetime(d.sched_dep_local)
            month = d.flight_date.dt.month
            valid = d.cancelled.eq(0) & d.diverted.eq(0) & d.arr_del15.isin([0, 1]) & np.isfinite(d.arr_delay_min)
            delayed = valid & d.arr_delay_min.ge(15)
            if (valid & d.arr_del15.ne(d.arr_delay_min.ge(15))).any():
                raise RuntimeError("Arrival label disagreement")
            matched = d.weather_match_status.eq("matched") & np.isfinite(d.weather_gap_minutes) & d.weather_gap_minutes.between(0, 90)
            all_rows = pd.Series(True, index=d.index)
            month_count(month, all_rows, "all_input")
            month_count(month, valid, "valid_arrivals_input")
            month_count(month, matched, "matched_all")
            month_count(month, matched & ~np.isfinite(d.precip_mm), "precip_nonfinite_matched_all")
            mask = all_rows.copy()
            record(STAGES[0], mask, valid, delayed)
            mask &= matched
            record(STAGES[1], mask, valid, delayed)
            for col in WEATHER:
                mask &= np.isfinite(d[col])
            record(STAGES[2], mask, valid, delayed)
            for col in QUALITY:
                mask &= d[col].isin(ACCEPTED)
            record(STAGES[3], mask, valid, delayed)
            mask &= d.wind_speed_kts.ge(0) & d.vis_m.ge(0)
            record(STAGES[4], mask, valid, delayed)
            controls = d.flight_date.dt.year.eq(2024) & d.sched_dep_local.notna() & d.sched_dep_local.dt.hour.between(0, 23)
            controls &= np.isfinite(d.distance_miles) & d.distance_miles.gt(0)
            for col in ["origin", "dest", "reporting_airline", "station_id"]:
                controls &= d[col].notna() & d[col].astype("string").str.strip().ne("").fillna(False)
            mask &= controls
            record(STAGES[5], mask, valid, delayed)
            precip_ok = np.isfinite(d.precip_mm) & d.precip_mm.ge(0) & d.precip_q.isin(ACCEPTED) & d.precip_period_h.eq(1)
            original_cohort_all += int((mask & precip_ok).sum())
            original_cohort_main += int((mask & precip_ok & valid).sum())
            month_count(month, mask, "expanded_all_outcomes")
            month_count(month, mask & valid, "expanded_main_arrivals")
            month_count(month, mask & delayed, "expanded_main_delayed")
            month_count(month, mask & valid & precip_ok, "original_precip_eligible_main")
            month_count(month, mask & valid & ~precip_ok, "additional_main_without_precip_filter")
            month_count(month, mask & valid & ~np.isfinite(d.precip_mm), "precip_nonfinite_expanded_main")
            s = d.loc[mask]
            main = valid.loc[mask]
            strict = pd.Series(True, index=s.index)
            for col in QUALITY:
                strict &= s[col].isin(STRICT)
            y_delay = np.where(main, s.arr_delay_min.ge(15).astype(np.int8), -1).astype(np.int8)
            y_severe = np.where(main, s.arr_delay_min.ge(60).astype(np.int8), -1).astype(np.int8)
            y_disrupt = np.where(s.cancelled.eq(1) | s.diverted.eq(1) | (y_delay == 1), 1,
                                 np.where(y_delay == 0, 0, -1)).astype(np.int8)
            origin, dest = s.origin.astype("string"), s.dest.astype("string")
            temp = (s.temp_c.astype(float) - 15) / 10
            out = pd.DataFrame({
                "date_id": (s.flight_date - pd.Timestamp("2024-01-01")).dt.days.astype(np.int16),
                "month": s.flight_date.dt.month.astype(np.int8),
                "weekday": (s.flight_date.dt.dayofweek + 1).astype(np.int8),
                "hour": s.sched_dep_local.dt.hour.astype(np.int8),
                "origin": origin, "dest": dest, "airline": s.reporting_airline.astype("string"),
                "station": s.station_id.astype("string"), "route": origin + "_" + dest,
                "distance_log": np.log(s.distance_miles / 500), "temp10": temp, "temp10sq": temp ** 2,
                "wind": np.select([s.wind_speed_kts.lt(5), s.wind_speed_kts.lt(10), s.wind_speed_kts.lt(20)], [0, 1, 2], default=3).astype(np.int8),
                "vis": np.select([s.vis_m.ge(10000), s.vis_m.ge(5000), s.vis_m.ge(1000)], [0, 1, 2], default=3).astype(np.int8),
                "rain": np.zeros(len(s), dtype=np.int8),
                "strict_q": strict.astype(np.int8), "within60": s.weather_gap_minutes.le(60).astype(np.int8),
                "y_delay": y_delay, "y_severe": y_severe, "y_disrupt": y_disrupt,
            })
            if out.isna().any().any():
                raise RuntimeError("Unexpected missing model value")
            out.to_csv(handle, index=False, header=not header_written, float_format="%.8g")
            header_written = True
            written += len(out)
            for col in ["wind", "vis", "strict_q", "within60", "y_delay", "y_severe", "y_disrupt"]:
                categories[col].update(out[col].value_counts().to_dict())
            print(f"Expanded batch {batch_n}: read {flow[STAGES[0]]['all_flights']:,}; wrote {written:,}; main {flow[STAGES[-1]]['valid_arrivals']:,}", flush=True)

    if original_cohort_main != 6_272_073 or original_cohort_all != 6_373_724:
        raise RuntimeError(f"Original main cohort failed reconciliation: {original_cohort_main}, {original_cohort_all}")
    flow_rows = []
    previous_all = previous_main = None
    for stage in STAGES:
        row = dict(flow[stage])
        row["removed_all_from_previous"] = 0 if previous_all is None else previous_all - row["all_flights"]
        row["removed_main_from_previous"] = 0 if previous_main is None else previous_main - row["valid_arrivals"]
        previous_all, previous_main = row["all_flights"], row["valid_arrivals"]
        flow_rows.append({"stage": stage, **row})
    month_rows = [{"month": m, **dict(c)} for m, c in sorted(monthly.items())]
    for row in month_rows:
        row["expanded_main_retention"] = row["expanded_main_arrivals"] / row["valid_arrivals_input"]
        row["original_main_retention"] = row["original_precip_eligible_main"] / row["valid_arrivals_input"]
    pd.DataFrame(flow_rows).to_csv(table_path / "no_precip_sample_flow.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(month_rows).to_csv(table_path / "no_precip_sample_by_month.csv", index=False, encoding="utf-8-sig")
    audit = {
        "status": "passed", "started_at": started, "completed_at": datetime.now().astimezone().isoformat(),
        "input": str(source_path), "input_sha256": source_sha, "input_rows": source.metadata.num_rows,
        "output": str(csv_path), "output_rows": written, "output_columns": list(out.columns),
        "expanded_main_arrivals": flow[STAGES[-1]]["valid_arrivals"],
        "expanded_main_delayed": flow[STAGES[-1]]["delayed_ge15"],
        "reconciled_original_all": original_cohort_all, "reconciled_original_main": original_cohort_main,
        "sample_flow": flow_rows, "sample_by_month": month_rows,
        "category_counts": {k: {str(v): int(n) for v, n in sorted(c.items())} for k, c in categories.items()},
        "weather_filter": "Finite temperature, wind, visibility; all three accepted quality codes in 0,1,4,5,A,C; nonnegative wind and visibility; matched observation 0–90 minutes before scheduled departure; positive distance and valid controls.",
        "precipitation_filter": "NONE: neither value completeness, quality code, nor accumulation-period restriction is imposed.",
        "rain_column": "CONSTANT ZERO PLACEHOLDER, not observed no precipitation. MUST BE EXCLUDED FROM ALL EXPANDED MODEL FORMULAS.",
        "strict_q": "All THREE included weather-element quality codes are in 1,5; differs from four-element strict_q in original CSV.",
        "source_checks": "SHA256 equals original preprocessed file. Full ID uniqueness and timestamp consistency checks are recorded in data_audit.json for this identical source; not rerun here.",
        "comparison_logic": "Compare no-precipitation formula on original vs expanded cohorts to isolate sample-composition differences; compare with-vs-without precipitation on original cohort to isolate specification differences. This does not identify missing-data causal effects.",
    }
    (table_path / "no_precip_data_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    code_dir = args.out.resolve() / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    dest_script = code_dir / "prepare_no_precip.py"
    if dest_script.resolve() != Path(__file__).resolve():
        shutil.copyfile(__file__, dest_script)
    print(json.dumps({"status": "passed", "expanded_rows": written, "main": flow[STAGES[-1]]["valid_arrivals"],
                      "main_delayed": flow[STAGES[-1]]["delayed_ge15"], "original_main_reconciled": original_cohort_main,
                      "output": str(csv_path)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
