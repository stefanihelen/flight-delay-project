# -*- coding: utf-8 -*-
"""
01_clean_bts.py — BTS 逐航班运行记录清洗（成员2 清洗与融合 子任务）

范围：仅清洗 BTS 2024 全年逐航班 CSV（data/raw/BTS/BTS_2024_full_year/）。
不做天气清洗、时区转换、空间融合（由其它并行子任务负责）。

用法：
    python cleaning/01_clean_bts.py --mode sample   # 跑小样本，写 cleaning/logs/bts_sample_check.txt
    python cleaning/01_clean_bts.py --mode full     # 逐月全量，写 cleaned parquet + 日志 + 统计

口径（勿改）：
- 取消(Cancelled==1)/备降(Diverted==1)/ArrTime 缺失一律不填为准点（不补 0）。
- arr_delay_min 取 ArrDelay，缺失即 NaN；arr_del15 取 ArrDel15(0/1)，缺失即 NaN。
- 一致性核对仅对“非取消、非备降、ArrDelay 与 ArrDel15 均非缺失”的行做：
  ArrDel15==1  <==>  ArrDelay>=15，不一致记 arr_del15_mismatch=1，其余=0。
- CRSDepTime 合法范围 0~2400；2400 表示次日 00:00。
    crs_dep_hhmm  : 原始整数（2400 保留）
    sched_dep_local: FlightDate + 分钟数（2400 -> 日期+1天 00:00），naive datetime。
- flight_id = {FlightDate}_{Reporting_Airline}_{Flight_Number_Reporting_Airline}_{Origin}_{Dest}_{CRSDepTime:04d}
  （flight_number 不补零，仅 CRSDepTime 补零到 4 位）。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
PROJECT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT / "data" / "raw" / "BTS" / "BTS_2024_full_year"
SAMPLE_CSV = PROJECT / "data" / "samples" / "raw" / "member1" / "BTS" / "bts_flights_sample.csv"
CLEANED_DIR = PROJECT / "data" / "cleaned"
MONTHLY_DIR = CLEANED_DIR / "bts_monthly"
MAIN_PARQUET = CLEANED_DIR / "bts_flights_2024.parquet"
LOG_CSV = CLEANED_DIR / "bts_cleaning_log.csv"
STATS_JSON = CLEANED_DIR / "bts_clean_stats.json"
LOGS_DIR = PROJECT / "cleaning" / "logs"
SAMPLE_CHECK_TXT = LOGS_DIR / "bts_sample_check.txt"
FINAL_CHECK_TXT = LOGS_DIR / "bts_final_check.txt"

MONTH_FILE = "On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2024_{m}.csv"

# 仅读取所需列，避免全表 object 膨胀
USECOLS = [
    "FlightDate", "Reporting_Airline", "Tail_Number",
    "Flight_Number_Reporting_Airline",
    "OriginAirportID", "DestAirportID",
    "Origin", "Dest", "OriginState", "DestState",
    "CRSDepTime", "ArrTime", "ArrDelay", "ArrDel15",
    "Cancelled", "Diverted", "Distance",
]
# 注：Flight_Number_Reporting_Airline 在 2024-08 有 1 行缺失（F9 MIA->ATL），
# 故用可空 Int64；读入后剔除身份键缺失行（无法构造 flight_id，无法下游关联）。
DTYPE = {
    "Reporting_Airline": "string",
    "Tail_Number": "string",
    "Origin": "string",
    "Dest": "string",
    "OriginState": "string",
    "DestState": "string",
    "OriginAirportID": "Int64",
    "DestAirportID": "Int64",
    "Flight_Number_Reporting_Airline": "Int64",
    "Cancelled": "int64",
    "Diverted": "int64",
    "Distance": "float64",
}

OUTPUT_COLUMNS = [
    "flight_id", "flight_date", "reporting_airline", "flight_number",
    "tail_number", "origin", "dest",
    "origin_airport_id", "dest_airport_id", "origin_state", "dest_state",
    "crs_dep_hhmm", "sched_dep_local", "distance_miles",
    "arr_delay_min", "arr_del15",
    "cancelled", "diverted", "arrival_time_missing", "arr_del15_mismatch",
]


def read_one(csv_path: Path) -> pd.DataFrame:
    """读单个 BTS CSV（utf-8-sig 处理 BOM）。"""
    df = pd.read_csv(
        csv_path,
        encoding="utf-8-sig",
        usecols=USECOLS,
        dtype=DTYPE,
        # CRSDepTime / ArrTime 可能有空值，这里按默认 float 解析后再显式转换
        low_memory=False,
    )
    return df


def _to_hhmm_int(series: pd.Series) -> pd.Series:
    """把 CRSDepTime/ArrTime（float 或字符串）转成可空整数 HHMM。"""
    s = pd.to_numeric(series, errors="coerce")
    return s.round().astype("Int64")


def clean_dataframe(df: pd.DataFrame):
    """
    对读入的单表执行全部清洗步骤。
    返回 (cleaned_df, stats_dict)。stats_dict 口径见模块 docstring。
    """
    raw_rows = len(df)

    # 1) 日期过滤：仅保留 FlightDate 年份 == 2024
    fd = df["FlightDate"].astype(str)
    year_ok = fd.str.slice(0, 4) == "2024"
    dropped_non2024 = int((~year_ok).sum())
    df = df.loc[year_ok].copy()

    # 1b) 剔除身份键缺失行（Flight_Number_Reporting_Airline 缺失 -> 无法构造 flight_id）
    miss_key = df["Flight_Number_Reporting_Airline"].isna()
    dropped_missing_key = int(miss_key.sum())
    if dropped_missing_key:
        df = df.loc[~miss_key].copy()

    # 2) CRSDepTime -> 整数 HHMM（2400 保留）
    crs = _to_hhmm_int(df["CRSDepTime"])
    df["crs_dep_hhmm"] = crs

    # 3) 去重：键=(FlightDate, Reporting_Airline, Flight_Number_Reporting_Airline,
    #                      Origin, Dest, crs_dep_hhmm)，保留首次出现
    before = len(df)
    df = df.drop_duplicates(
        subset=["FlightDate", "Reporting_Airline",
                "Flight_Number_Reporting_Airline", "Origin", "Dest", "crs_dep_hhmm"],
        keep="first",
    ).copy()
    dup_dropped = before - len(df)

    # 4) sched_dep_local = FlightDate + 分钟数（2400 -> 次日 00:00）
    flight_date = pd.to_datetime(df["FlightDate"].astype(str), format="%Y-%m-%d")
    hh = (df["crs_dep_hhmm"] // 100).astype("int64")
    mm = (df["crs_dep_hhmm"] % 100).astype("int64")
    total_min = hh * 60 + mm
    df["sched_dep_local"] = flight_date + pd.to_timedelta(total_min, unit="m")

    # 5) 状态与延误标记
    cancelled = (df["Cancelled"] == 1).astype("int8")
    diverted = (df["Diverted"] == 1).astype("int8")
    arr_time_missing = df["ArrTime"].isna().astype("int8")

    arr_delay_min = pd.to_numeric(df["ArrDelay"], errors="coerce")
    arr_del15 = pd.to_numeric(df["ArrDel15"], errors="coerce")
    # arr_del15 规范为 0/1（缺失保留 NaN）
    arr_del15 = arr_del15.where(arr_del15.isna(), arr_del15.round().astype("float64"))

    # 一致性核对：仅对 非取消 & 非备降 & ArrDelay/ArrDel15 均非缺失 的行
    valid = (cancelled == 0) & (diverted == 0) & arr_delay_min.notna() & arr_del15.notna()
    expected_flag = (arr_delay_min >= 15).astype("float64")
    mismatch = pd.Series(0, index=df.index, dtype="int8")
    mismatch[valid] = (arr_del15[valid] != expected_flag[valid]).astype("int8")

    # 6) flight_id（flight_number 原样，CRSDepTime 补零 4 位）
    crs_str = df["crs_dep_hhmm"].astype("int64").map(lambda x: f"{x:04d}")
    flight_id = (
        df["FlightDate"].astype(str) + "_"
        + df["Reporting_Airline"].astype(str) + "_"
        + df["Flight_Number_Reporting_Airline"].astype(str) + "_"
        + df["Origin"].astype(str) + "_"
        + df["Dest"].astype(str) + "_"
        + crs_str
    )

    # 7) 组装输出
    out = pd.DataFrame({
        "flight_id": flight_id.values,
        "flight_date": flight_date.dt.date,           # 日期类型
        "reporting_airline": df["Reporting_Airline"].astype(str).values,
        "flight_number": df["Flight_Number_Reporting_Airline"].astype("int64").values,
        "tail_number": df["Tail_Number"].astype(str).values,
        "origin": df["Origin"].astype(str).values,
        "dest": df["Dest"].astype(str).values,
        "origin_airport_id": df["OriginAirportID"].astype("int64").values,
        "dest_airport_id": df["DestAirportID"].astype("int64").values,
        "origin_state": df["OriginState"].astype(str).values,
        "dest_state": df["DestState"].astype(str).values,
        "crs_dep_hhmm": df["crs_dep_hhmm"].astype("int64").values,
        "sched_dep_local": df["sched_dep_local"].values,
        "distance_miles": pd.to_numeric(df["Distance"], errors="coerce").values,
        "arr_delay_min": arr_delay_min.values,
        "arr_del15": arr_del15.values,
        "cancelled": cancelled.values,
        "diverted": diverted.values,
        "arrival_time_missing": arr_time_missing.values,
        "arr_del15_mismatch": mismatch.values,
    })[OUTPUT_COLUMNS]

    stats = {
        "raw_rows": int(raw_rows),
        "kept_rows": int(len(out)),
        "dropped_non2024": dropped_non2024,
        "dropped_missing_key": dropped_missing_key,
        "dup_dropped": int(dup_dropped),
        "n_crs2400": int((df["crs_dep_hhmm"] == 2400).sum()),
        "cancelled": int((out["cancelled"] == 1).sum()),
        "diverted": int((out["diverted"] == 1).sum()),
        "arr_time_missing": int((out["arrival_time_missing"] == 1).sum()),
        "arr_del15_mismatch": int((out["arr_del15_mismatch"] == 1).sum()),
    }
    return out, stats


# ---------------------------------------------------------------------------
# sample 模式
# ---------------------------------------------------------------------------
def run_sample():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SAMPLE_CSV, encoding="utf-8-sig", usecols=USECOLS,
                     dtype=DTYPE, low_memory=False)
    out, stats = clean_dataframe(df)

    lines = []
    lines.append("BTS 小样本清洗检查 (bts_flights_sample.csv)")
    lines.append("=" * 60)
    lines.append(f"输入文件: {SAMPLE_CSV}")
    lines.append(f"输入原始行数: {stats['raw_rows']}")
    lines.append(f"清洗后保留行数: {stats['kept_rows']}")
    lines.append(f"剔除非2024行数: {stats['dropped_non2024']}")
    lines.append(f"去重剔除行数: {stats['dup_dropped']}")
    lines.append(f"CRSDepTime==2400 航班数: {stats['n_crs2400']}")
    lines.append(f"cancelled 数: {stats['cancelled']}")
    lines.append(f"diverted 数: {stats['diverted']}")
    lines.append(f"arrival_time_missing 数: {stats['arr_time_missing']}")
    lines.append(f"arr_del15_mismatch 数: {stats['arr_del15_mismatch']}")
    lines.append("")
    lines.append("清洗后列: " + ", ".join(out.columns))
    lines.append("")
    lines.append("清洗后前 5 行:")
    with pd.option_context("display.max_columns", None, "display.width", 200,
                           "display.max_colwidth", 30):
        lines.append(out.head(5).to_string(index=False))
    lines.append("")
    lines.append("flight_id 唯一性检查: "
                 f"unique={out['flight_id'].is_unique}, n={len(out)}")
    txt = "\n".join(str(x) for x in lines) + "\n"
    SAMPLE_CHECK_TXT.write_text(txt, encoding="utf-8")
    print(txt)
    print(f"[written] {SAMPLE_CHECK_TXT}")


# ---------------------------------------------------------------------------
# full 模式
# ---------------------------------------------------------------------------
def run_full():
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_rows = []
    kept_total = 0
    raw_total = 0
    for m in range(1, 13):
        csv_path = RAW_DIR / MONTH_FILE.format(m=m)
        if not csv_path.exists():
            raise FileNotFoundError(f"缺少月度 CSV: {csv_path}")
        print(f"[{m:02d}] reading {csv_path.name} ...", flush=True)
        df = read_one(csv_path)
        out, stats = clean_dataframe(df)
        out_path = MONTHLY_DIR / f"2024_{m:02d}.parquet"
        out.to_parquet(out_path, engine="pyarrow", compression="snappy", index=False)
        print(f"     raw={stats['raw_rows']} kept={stats['kept_rows']} "
              f"dup={stats['dup_dropped']} 2400={stats['n_crs2400']} "
              f"-> {out_path.name}", flush=True)
        row = {"month": f"2024-{m:02d}", **stats}
        log_rows.append(row)
        kept_total += stats["kept_rows"]
        raw_total += stats["raw_rows"]
        # 释放内存
        del df, out

    # 写月度日志 CSV（按任务书要求列序；另附 dropped_missing_key 以保持可追溯）
    log_df = pd.DataFrame(log_rows)[
        ["month", "raw_rows", "kept_rows", "dropped_non2024", "dropped_missing_key",
         "dup_dropped", "n_crs2400", "cancelled", "diverted", "arr_time_missing",
         "arr_del15_mismatch"]
    ]
    log_df.to_csv(LOG_CSV, index=False, encoding="utf-8-sig")

    # 合并 12 个月度 parquet
    monthly_files = sorted(MONTHLY_DIR.glob("2024_*.parquet"))
    parts = [pd.read_parquet(p) for p in monthly_files]
    merged = pd.concat(parts, ignore_index=True)
    merged.to_parquet(MAIN_PARQUET, engine="pyarrow", compression="snappy",
                       index=False)

    # 核对行数
    sum_monthly = sum(len(p) for p in parts)
    assert sum_monthly == len(merged), \
        f"合并行数不一致: 月度和={sum_monthly} 合并={len(merged)}"
    assert len(merged) == kept_total, \
        f"kept_total 不一致: {kept_total} vs {len(merged)}"

    # 全年汇总统计
    stats_sum = {
        "raw_rows_total": int(raw_total),
        "kept_rows_total": int(len(merged)),
        "dropped_non2024_total": int(log_df["dropped_non2024"].sum()),
        "dropped_missing_key_total": int(log_df["dropped_missing_key"].sum()),
        "dup_dropped_total": int(log_df["dup_dropped"].sum()),
        "n_crs2400_total": int(log_df["n_crs2400"].sum()),
        "cancelled_total": int(log_df["cancelled"].sum()),
        "diverted_total": int(log_df["diverted"].sum()),
        "arr_time_missing_total": int(log_df["arr_time_missing"].sum()),
        "arr_del15_mismatch_total": int(log_df["arr_del15_mismatch"].sum()),
        "flight_id_unique": bool(merged["flight_id"].is_unique),
        "n_months": len(monthly_files),
    }
    STATS_JSON.write_text(
        json.dumps(stats_sum, ensure_ascii=False, indent=2), encoding="utf-8")

    # 自检：读回主 parquet
    chk = pd.read_parquet(MAIN_PARQUET)
    lines = []
    lines.append("BTS 全年清洗自检 (读回 bts_flights_2024.parquet)")
    lines.append("=" * 60)
    lines.append(f"文件: {MAIN_PARQUET}")
    lines.append(f"行数: {len(chk)}")
    lines.append(f"列数: {chk.shape[1]}")
    lines.append("")
    lines.append("核心列非空率:")
    for c in chk.columns:
        non_null = chk[c].notna().mean() * 100
        lines.append(f"  {c:24s} {non_null:6.2f}%  (dtype={chk[c].dtype})")
    lines.append("")
    lines.append(f"flight_id 唯一: {chk['flight_id'].is_unique}")
    lines.append(f"月度行数之和 == 合并行数: {sum_monthly} == {len(chk)}")
    lines.append(f"剔除非2024总行数: {stats_sum['dropped_non2024_total']}")
    lines.append(f"剔除身份键缺失总行数: {stats_sum['dropped_missing_key_total']}")
    lines.append(f"去重剔除总行数: {stats_sum['dup_dropped_total']}")
    lines.append("")
    lines.append("前 3 行样例:")
    with pd.option_context("display.max_columns", None, "display.width", 220,
                           "display.max_colwidth", 28):
        lines.append(chk.head(3).to_string(index=False))
    txt = "\n".join(str(x) for x in lines) + "\n"
    FINAL_CHECK_TXT.write_text(txt, encoding="utf-8")

    print(txt)
    print(f"[written] {LOG_CSV}")
    print(f"[written] {STATS_JSON}")
    print(f"[written] {MAIN_PARQUET}")
    print(f"[written] {FINAL_CHECK_TXT}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["sample", "full"], required=True)
    args = ap.parse_args()
    if args.mode == "sample":
        run_sample()
    else:
        run_full()


if __name__ == "__main__":
    main()
