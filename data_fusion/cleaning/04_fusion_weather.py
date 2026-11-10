# -*- coding: utf-8 -*-
"""
04_fusion_weather.py
成员2 "清洗与融合" 模块 —— 融合与天气匹配（串行流水第三波）

输入（只读，前序子任务产物）：
  data/cleaned/bts_flights_2024.parquet            7,079,060 行
  data/cleaned/noaa_obs_2024.parquet               3,905,968 行（FM-15/FM-16）
  data/cleaned/airport_timezones.csv               348 机场 IANA 时区
  data/cleaned/airport_state_check.csv             348 机场州界核验
  metadata/airport_station_mapping_reviewed.csv    348 机场-站点修订映射
  metadata/noaa_full_airports_2024.csv             正式 346 站清单

输出（新增，不覆盖任何既有文件）：
  data/integrated/flights_weather_2024.parquet     一行一班，7,079,060 行
  data/integrated/flights_weather_2024_sample.csv  前 20,000 行查看样本
  data/integrated/fusion_stats.json                融合统计
  cleaning/logs/fusion_check.txt                   抽样核验与自检日志

运行（项目根目录下）：
  python cleaning/04_fusion_weather.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "cleaning" / "logs" / "fusion_check.txt"
OUT_DIR = ROOT / "data" / "integrated"
OUT_DIR.mkdir(parents=True, exist_ok=True)

log_lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    log_lines.append(str(msg))


EXPECTED_FLIGHT_ROWS = 7_079_060


def main() -> int:
    log("=" * 78)
    log("04_fusion_weather.py  航班-天气融合（一行一班）")
    log("=" * 78)

    # ------------------------------------------------------------------
    # 1. 读取输入
    # ------------------------------------------------------------------
    log("\n[1] 读取输入 ...")
    flights = pd.read_parquet(ROOT / "data/cleaned/bts_flights_2024.parquet")
    log(f"  BTS flights: {flights.shape}")
    assert len(flights) == EXPECTED_FLIGHT_ROWS, f"BTS 行数 {len(flights)} != 预期 {EXPECTED_FLIGHT_ROWS}"

    obs = pd.read_parquet(ROOT / "data/cleaned/noaa_obs_2024.parquet")
    log(f"  NOAA obs   : {obs.shape}")

    tz_df = pd.read_csv(ROOT / "data/cleaned/airport_timezones.csv", dtype=str)
    state_df = pd.read_csv(ROOT / "data/cleaned/airport_state_check.csv", dtype=str)
    mapping_df = pd.read_csv(ROOT / "metadata/airport_station_mapping_reviewed.csv", dtype=str)
    full_df = pd.read_csv(ROOT / "metadata/noaa_full_airports_2024.csv", dtype=str)
    log(f"  tz={tz_df.shape}, state_check={state_df.shape}, mapping={mapping_df.shape}, full346={full_df.shape}")

    # 保留原始行序
    flights = flights.reset_index(drop=True)
    flights["_orig_order"] = np.arange(len(flights), dtype=np.int64)

    # ------------------------------------------------------------------
    # 2. 关联时区 / 州界 / 站点映射
    # ------------------------------------------------------------------
    log("\n[2] 关联时区、州界、站点映射 ...")
    tz_map = dict(zip(tz_df["airport_code"], tz_df["tz_iana"]))
    poly_map = dict(zip(state_df["airport_code"], state_df["polygon_state"]))
    station_map = dict(zip(mapping_df["airport_code"], mapping_df["station_id"]))
    full_station_set = set(full_df["station_id"].dropna())

    flights["origin_tz_iana"] = flights["origin"].map(tz_map)
    flights["origin_polygon_state"] = flights["origin"].map(poly_map)
    flights["station_id"] = flights["origin"].map(station_map)

    n_tz_missing = int(flights["origin_tz_iana"].isna().sum())
    n_poly_missing = int(flights["origin_polygon_state"].isna().sum())
    n_station_missing = int(flights["station_id"].isna().sum())
    log(f"  origin_tz_iana 缺失行数: {n_tz_missing}")
    log(f"  origin_polygon_state 缺失行数: {n_poly_missing}")
    log(f"  station_id 缺失行数(XWA): {n_station_missing}")

    # 可用站点：station_id 非空 且 在正式 346 清单内
    flights["_has_station"] = flights["station_id"].notna()
    flights["_usable_station"] = flights["station_id"].isin(full_station_set)
    n_usable = int(flights["_usable_station"].sum())
    n_no_station = int((~flights["_has_station"]).sum())
    n_station_not_usable = int((flights["_has_station"] & ~flights["_usable_station"]).sum())
    log(f"  有可用站点(在346清单内)航班: {n_usable}")
    log(f"  无站点(XWA)航班: {n_no_station}")
    log(f"  有站点但不在346清单(SGU)航班: {n_station_not_usable}")
    # 列出具体机场
    bad_airports = flights.loc[flights["_has_station"] & ~flights["_usable_station"], "origin"].unique().tolist()
    log(f"    -> 不在346清单的机场: {bad_airports}")
    no_stn_airports = flights.loc[~flights["_has_station"], "origin"].unique().tolist()
    log(f"    -> 无站点机场: {no_stn_airports}")

    # ------------------------------------------------------------------
    # 3. 时区转换：naive local -> UTC（按起飞机场 IANA，正确处理夏令时）
    # ------------------------------------------------------------------
    log("\n[3] 时区转换 sched_dep_local -> dep_utc ...")
    dep_utc = pd.Series(pd.NaT, index=flights.index, dtype="datetime64[us]")
    tz_groups = flights.groupby("origin_tz_iana").groups
    for tz_name, idx in tz_groups.items():
        if tz_name is None or (isinstance(tz_name, float) and pd.isna(tz_name)):
            continue
        sub = flights.loc[idx, ["sched_dep_local"]].sort_values("sched_dep_local")
        # ambiguous=False: 夏令时回退夜(11月第一个周日 1:00-1:59 本地钟点出现两次)
        # 确定性地按标准时间(后一次出现, 如 PST=UTC-8)解释；nonexistent(春调 2:00-2:59 不存在)记 NaT
        loc = sub["sched_dep_local"].dt.tz_localize(
            tz_name, ambiguous=False, nonexistent="NaT"
        )
        utc = loc.dt.tz_convert("UTC").dt.tz_localize(None)
        dep_utc.loc[sub.index] = utc.values
    flights["dep_utc"] = dep_utc

    n_dep_utc_nat = int(flights["dep_utc"].isna().sum())
    log(f"  dep_utc 为 NaT 的行数: {n_dep_utc_nat}")
    if n_dep_utc_nat > 0:
        bad = flights.loc[flights["dep_utc"].isna(), ["origin", "origin_tz_iana", "sched_dep_local"]]
        log(f"  dep_utc NaT 样例:\n{bad.head(10).to_string()}")

    # ------------------------------------------------------------------
    # 4. NOAA 观测去重：同 (station_id, obs_utc) 优先 FM-15
    # ------------------------------------------------------------------
    log("\n[4] NOAA 观测按 (station_id, obs_utc) 去重，优先 FM-15 ...")
    n_obs_before = len(obs)
    obs = obs.sort_values(["station_id", "obs_utc", "report_type"], kind="mergesort")
    obs = obs.drop_duplicates(subset=["station_id", "obs_utc"], keep="first").reset_index(drop=True)
    log(f"  去重前 {n_obs_before} -> 去重后 {len(obs)}（移除 {n_obs_before - len(obs)} 条重复时刻）")
    obs = obs.sort_values("obs_utc").reset_index(drop=True)

    # ------------------------------------------------------------------
    # 5. 天气匹配：merge_asof backward，obs_utc <= dep_utc，窗口 90 分钟
    # ------------------------------------------------------------------
    log("\n[5] merge_asof 天气匹配 ...")
    weather_cols = [
        "temp_c", "temp_q", "dew_c", "dew_q", "slp_hpa", "slp_q",
        "wind_dir_deg", "wind_dir_q", "wind_speed_kts", "wind_speed_q",
        "vis_m", "vis_q", "precip_mm", "precip_q", "precip_period_h", "precip_reported",
    ]
    # 初始化天气列：数值列用 float64+NaN；质量码(字符串)列用 object+pd.NA
    numeric_weather = ["temp_c", "dew_c", "slp_hpa", "wind_dir_deg",
                       "wind_speed_kts", "vis_m", "precip_mm", "precip_period_h"]
    str_weather = ["temp_q", "dew_q", "slp_q", "wind_dir_q", "wind_speed_q",
                   "vis_q", "precip_q"]
    for c in numeric_weather:
        flights[c] = np.nan
    for c in str_weather:
        flights[c] = pd.Series(pd.NA, index=flights.index, dtype="object")
    flights["precip_reported"] = np.nan
    flights["weather_obs_utc"] = pd.NaT
    flights["weather_gap_minutes"] = np.nan
    flights["weather_match_within_60"] = False

    # 默认状态
    wms = np.where(
        ~flights["_has_station"], "no_station",
        np.where(~flights["_usable_station"], "no_station_usable", "pending"),
    )
    flights["weather_match_status"] = wms

    eligible_mask = flights["_usable_station"] & flights["dep_utc"].notna()
    elig = flights.loc[eligible_mask, ["_orig_order", "station_id", "dep_utc"]].copy()
    elig = elig.sort_values("dep_utc").reset_index(drop=True)
    log(f"  参与 asof 匹配的航班: {len(elig)}")

    if len(elig) > 0:
        merged = pd.merge_asof(
            elig,
            obs,
            left_on="dep_utc",
            right_on="obs_utc",
            by="station_id",
            direction="backward",
            allow_exact_matches=True,
        )
        merged["weather_gap_minutes"] = (
            merged["dep_utc"] - merged["obs_utc"]
        ).dt.total_seconds() / 60.0

        is_matched = merged["obs_utc"].notna() & (merged["weather_gap_minutes"] <= 90.0)
        merged["_status"] = np.where(is_matched, "matched", "no_obs_within_90")

        # 写回 flights
        idx = merged["_orig_order"].values
        flights.loc[idx, "weather_obs_utc"] = merged["obs_utc"].values
        flights.loc[idx, "weather_gap_minutes"] = merged["weather_gap_minutes"].values
        for c in weather_cols:
            flights.loc[idx, c] = merged[c].values
        flights.loc[idx, "weather_match_status"] = merged["_status"].values
        flights.loc[idx, "weather_match_within_60"] = (
            merged["_status"].eq("matched") & (merged["weather_gap_minutes"] <= 60.0)
        ).values

    # 剩余 pending（usable 但 dep_utc 为 NaT）-> no_obs_within_90
    flights.loc[flights["weather_match_status"] == "pending", "weather_match_status"] = "no_obs_within_90"

    # ------------------------------------------------------------------
    # 6. 硬校验：行数不变、flight_id 唯一
    # ------------------------------------------------------------------
    log("\n[6] 硬校验 ...")
    n_final = len(flights)
    n_unique_fid = flights["flight_id"].is_unique
    log(f"  最终行数: {n_final}")
    log(f"  flight_id 唯一: {n_unique_fid}")
    assert n_final == EXPECTED_FLIGHT_ROWS, f"融合后行数 {n_final} != {EXPECTED_FLIGHT_ROWS}"
    assert n_unique_fid, "flight_id 不唯一！融合产生了重复行"
    assert flights["_orig_order"].is_monotonic_increasing

    # ------------------------------------------------------------------
    # 7. 输出列契约
    # ------------------------------------------------------------------
    out_cols = [
        "flight_id", "flight_date", "reporting_airline", "flight_number", "tail_number",
        "origin", "dest", "origin_airport_id", "dest_airport_id",
        "origin_state", "dest_state", "origin_polygon_state", "origin_tz_iana",
        "crs_dep_hhmm", "sched_dep_local", "dep_utc", "distance_miles",
        "arr_delay_min", "arr_del15", "cancelled", "diverted",
        "arrival_time_missing", "arr_del15_mismatch",
        "weather_match_status", "station_id", "weather_obs_utc",
        "weather_gap_minutes", "weather_match_within_60",
        "temp_c", "temp_q", "dew_c", "dew_q", "slp_hpa", "slp_q",
        "wind_dir_deg", "wind_dir_q", "wind_speed_kts", "wind_speed_q",
        "vis_m", "vis_q", "precip_mm", "precip_q", "precip_period_h", "precip_reported",
    ]
    out = flights[out_cols].copy()

    # 高效 dtype
    for c in ["reporting_airline", "origin", "dest", "origin_state", "dest_state",
              "origin_polygon_state", "origin_tz_iana", "weather_match_status",
              "station_id", "temp_q", "dew_q", "slp_q", "wind_dir_q", "wind_speed_q",
              "vis_q", "precip_q"]:
        out[c] = out[c].astype("category")
    for c in ["temp_c", "dew_c", "slp_hpa", "wind_dir_deg", "wind_speed_kts",
              "vis_m", "precip_mm", "precip_period_h", "weather_gap_minutes"]:
        out[c] = out[c].astype("float32")

    parquet_path = OUT_DIR / "flights_weather_2024.parquet"
    out.to_parquet(parquet_path, index=False, compression="zstd")
    log(f"  写出 parquet: {parquet_path}  shape={out.shape}")

    sample = out.head(20_000).copy()
    csv_path = OUT_DIR / "flights_weather_2024_sample.csv"
    sample.to_csv(csv_path, index=False, encoding="utf-8-sig")
    log(f"  写出样本CSV: {csv_path}  shape={sample.shape}（前20,000行，仅查看样本非全量）")

    # ------------------------------------------------------------------
    # 8. 抽样人工核验
    # ------------------------------------------------------------------
    log("\n[7] 抽样核验 ...")
    verify_cases = []

    def tz_verify(airport: str, local_dt: str, expect_utc: str, label: str) -> None:
        m = flights[(flights["origin"] == airport) &
                    (flights["sched_dep_local"] == pd.Timestamp(local_dt))]
        if len(m) == 0:
            # 尝试同机场该日期附近
            d = pd.Timestamp(local_dt).date()
            m = flights[(flights["origin"] == airport) &
                        (flights["sched_dep_local"].dt.date == d)].head(1)
        if len(m) == 0:
            log(f"  [TZ MISS] {airport} {local_dt} 未找到航班")
            verify_cases.append({"airport": airport, "local": local_dt,
                                 "expected_utc": expect_utc, "found": False})
            return
        r = m.iloc[0]
        got = r["dep_utc"]
        got_str = got.strftime("%Y-%m-%d %H:%M") if pd.notna(got) else "NaT"
        ok = got_str == expect_utc
        log(f"  [TZ {'OK' if ok else 'XX'}] {label}: {airport} local={r['sched_dep_local']} "
            f"tz={r['origin_tz_iana']} -> utc={got_str}  (期望 {expect_utc})")
        verify_cases.append({"airport": airport, "local": str(r["sched_dep_local"]),
                             "tz": r["origin_tz_iana"], "got_utc": got_str,
                             "expected_utc": expect_utc, "found": True, "ok": bool(ok)})

    tz_verify("JFK", "2024-01-09 09:00", "2024-01-09 14:00", "JFK冬季EST")
    tz_verify("ORD", "2024-07-09 12:00", "2024-07-09 17:00", "ORD夏季CDT")
    tz_verify("LAX", "2024-07-09 10:00", "2024-07-09 17:00", "LAX夏季PDT")
    tz_verify("PHX", "2024-07-09 10:00", "2024-07-09 17:00", "PHX无DST MST")

    # 2400 跨日航班：找 crs_dep_hhmm 接近 2400 且 sched_dep_local 为次日 00:xx 的航班
    m2400 = flights[flights["sched_dep_local"].dt.hour == 0].head(1)
    if len(m2400) > 0:
        r = m2400.iloc[0]
        log(f"  [2400跨日样例] flight_id={r['flight_id']} origin={r['origin']} "
            f"crs_dep_hhmm={r['crs_dep_hhmm']} sched_dep_local={r['sched_dep_local']} "
            f"tz={r['origin_tz_iana']} dep_utc={r['dep_utc']}")
        verify_cases.append({"type": "2400_crossday", "flight_id": r["flight_id"],
                             "origin": r["origin"], "crs_dep_hhmm": int(r["crs_dep_hhmm"]),
                             "sched_dep_local": str(r["sched_dep_local"]),
                             "tz": r["origin_tz_iana"],
                             "dep_utc": str(r["dep_utc"])})

    # 天气匹配抽样：取 3 条 matched 航班
    log("  天气匹配抽样:")
    wverify = []
    matched_df = flights[flights["weather_match_status"] == "matched"]
    for _, r in matched_df.head(3).iterrows():
        log(f"    {r['flight_id']} origin={r['origin']} station={r['station_id']} "
            f"dep_utc={r['dep_utc']} obs_utc={r['weather_obs_utc']} "
            f"gap={r['weather_gap_minutes']:.1f}min temp={r['temp_c']} vis={r['vis_m']}")
        wverify.append({
            "flight_id": r["flight_id"], "origin": r["origin"], "station": r["station_id"],
            "dep_utc": str(r["dep_utc"]), "obs_utc": str(r["weather_obs_utc"]),
            "gap_minutes": float(r["weather_gap_minutes"]),
            "temp_c": None if pd.isna(r["temp_c"]) else float(r["temp_c"]),
            "vis_m": None if pd.isna(r["vis_m"]) else float(r["vis_m"]),
        })
    # XWA / SGU 状态抽样
    for code in ["XWA", "SGU", "WYS"]:
        sub = flights[flights["origin"] == code]
        if len(sub) > 0:
            r = sub.iloc[0]
            cnt = sub["weather_match_status"].value_counts().to_dict()
            log(f"    {code}: {len(sub)} 班, status分布={cnt}, station_id={r['station_id']}")
            wverify.append({"airport": code, "flights": int(len(sub)),
                            "status_counts": cnt, "station_id": r["station_id"]})

    # ------------------------------------------------------------------
    # 9. 统计
    # ------------------------------------------------------------------
    log("\n[8] 计算统计 ...")
    total = len(flights)
    status_counts = flights["weather_match_status"].value_counts().to_dict()
    status_pct = {k: round(v / total * 100, 3) for k, v in status_counts.items()}

    n_usable_flights = int(flights["_usable_station"].sum())
    n_matched = int((flights["weather_match_status"] == "matched").sum())
    n_matched_60 = int((flights["weather_match_within_60"] == True).sum())  # noqa: E712

    gap = flights.loc[flights["weather_match_status"] == "matched", "weather_gap_minutes"].astype(float)
    gap_q = gap.quantile([0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0]).round(2).to_dict()
    gap_dist = {
        "min": float(gap.min()), "p10": float(gap.quantile(0.10)),
        "p25": float(gap.quantile(0.25)), "median": float(gap.quantile(0.50)),
        "p75": float(gap.quantile(0.75)), "p90": float(gap.quantile(0.90)),
        "max": float(gap.max()),
    }
    n_m = len(gap)
    gap_bins = {
        "0_30_min_pct": round(float(((gap >= 0) & (gap <= 30)).sum() / n_m * 100), 3),
        "30_60_min_pct": round(float(((gap > 30) & (gap <= 60)).sum() / n_m * 100), 3),
        "60_90_min_pct": round(float(((gap > 60) & (gap <= 90)).sum() / n_m * 100), 3),
    }

    # matched 子集关键变量缺失率与质量码分布
    m_df = flights[flights["weather_match_status"] == "matched"]
    miss = {}
    for c in ["temp_c", "vis_m", "wind_speed_kts", "precip_mm"]:
        miss[c + "_missing_pct"] = round(float(m_df[c].isna().sum() / len(m_df) * 100), 3)
    qdist = {}
    for c in ["temp_q", "vis_q", "wind_speed_q", "precip_q"]:
        qdist[c] = m_df[c].value_counts(dropna=False).to_dict()

    # 州界一致性
    both = flights[["origin_state", "origin_polygon_state"]].dropna()
    consistent = int((both["origin_state"] == both["origin_polygon_state"]).sum())
    inconsistent = int((both["origin_state"] != both["origin_polygon_state"]).sum())
    tt = int(flights["origin_state"].eq("TT").sum())

    stats = {
        "flight_total": total,
        "weather_match_status_counts": status_counts,
        "weather_match_status_pct": status_pct,
        "airport_match_rate": {
            "flights_with_usable_station": n_usable_flights,
            "pct": round(n_usable_flights / total * 100, 3),
        },
        "weather_match_rate_90min": {
            "matched": n_matched,
            "pct": round(n_matched / total * 100, 3),
        },
        "weather_match_rate_60min": {
            "matched_within_60": n_matched_60,
            "pct": round(n_matched_60 / total * 100, 3),
        },
        "gap_minutes_distribution_matched_only": gap_dist,
        "gap_minutes_bins_pct": gap_bins,
        "key_variable_missing_pct_in_matched": miss,
        "quality_code_dist_in_matched": qdist,
        "timezone": {
            "dep_utc_nat_count": n_dep_utc_nat,
            "origin_tz_missing_rows": n_tz_missing,
            "ambiguous_fallback_rule": "夏令时回退夜(11月第一个周日 1:00-1:59 本地)按标准时间解释(ambiguous=False)",
        },
        "state_check": {
            "consistent_rows": consistent,
            "inconsistent_rows": inconsistent,
            "TT_origin_rows": tt,
            "note": "origin_polygon_state 取自 airport_state_check.csv 的 polygon_state 列；"
                    "TT 三机场(GUM/PPG/SPN)为 BTS 领地代码，polygon 分别为 GU/AS/MP",
        },
        "observations_dedup": {
            "before": n_obs_before,
            "after": len(obs),
        },
        "sample_verification": {
            "timezone_cases": verify_cases,
            "weather_cases": wverify,
        },
        "exceptions": {
            "XWA_no_station": int(n_no_station),
            "SGU_no_station_usable": int(n_station_not_usable),
            "WYS_partial_coverage_note": "WYS/72676494163 仅 2024-04-29~11-06 有观测，"
                                         "覆盖外时段自然落入 no_obs_within_90，不补造天气",
        },
    }

    stats_path = OUT_DIR / "fusion_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)
    log(f"  写出统计: {stats_path}")

    # ------------------------------------------------------------------
    # 10. 自检：重读主 parquet
    # ------------------------------------------------------------------
    log("\n[9] 自检：重读主 parquet ...")
    chk = pd.read_parquet(parquet_path)
    log(f"  重读 shape: {chk.shape}")
    log(f"  flight_id 唯一: {chk['flight_id'].is_unique}")
    log(f"  weather_match_status 分布: {chk['weather_match_status'].value_counts().to_dict()}")
    log(f"  列数: {len(chk.columns)}")
    log(f"  样例首行: {chk.iloc[0][['flight_id','origin','dep_utc','weather_match_status','weather_gap_minutes']].to_dict()}")
    assert chk.shape[0] == EXPECTED_FLIGHT_ROWS
    assert chk["flight_id"].is_unique

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    log(f"\n日志已写入: {LOG_PATH}")
    log("\n全部完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
