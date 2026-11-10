# -*- coding: utf-8 -*-
"""
02_clean_noaa.py — NOAA ISD Global-Hourly 2024 天气观测清洗（成员2/清洗与融合模块）

解析规则逐条来自官方文档 ISD Format Document
(https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf)，代码内注释出处：

- TMP  (AIR-TEMPERATURE-OBSERVATION air temperature, 文档p.10):
        5位有符号码, UNITS Degrees Celsius, SCALING FACTOR 10  =>  temp_c = code/10
        缺失码 +9999 = Missing。质量码 0/1/2/3/4/5/6/7/9/A/C/I/M。
- DEW  (AIR-TEMPERATURE-OBSERVATION dew point temperature, 文档p.10):
        同上, 范围 -982~+368,  +9999 = Missing。
- SLP  (ATMOSPHERIC-PRESSURE-OBSERVATION sea level pressure):
        5位无符号码, UNITS Hectopascals, SCALING FACTOR 10 => slp_hpa = code/10
        缺失码 99999 = Missing。
- WND  (WIND-OBSERVATION, 文档 Wind Data 节):
        direction angle: 3位, UNITS Angular Degrees, SCALING 1, 999=Missing
        direction quality code: 1位
        type code: 1位 (A/B/C/H/N/R/Q/T/V/9)
        speed rate: 4位, UNITS meters per second, SCALING FACTOR 10, 9999=Missing
        speed quality code: 1位
        输出风速统一换算为 knots: kts = (mps_code/10) * 1.94384449244 (1 m/s = 1.943844 knots)
- VIS  (VISIBILITY-OBSERVATION distance dimension, 文档 p.85):
        6位, MIN 000000 MAX 160000, UNITS: Meters（文档未列 SCALING FACTOR，即码值直接=米）
        Missing = 999999；NOTE: >160000 记为 160000。
        distance quality code(1) / variability(N/V/9)(1) / variability quality(1)。
        【注】任务书早期曾写"VIS×10"，与官方文档矛盾；以官方文档为准，
              码值直接=米（实证：ATL FM-15 VIS=016093 对应 METAR 10SM=16093m）。
- AA1  (LIQUID-PRECIPITATION occurrence identifier, 文档 Precipitation Data 节):
        period quantity: 2位, UNITS Hours, 99=Missing
        depth dimension: 4位, UNITS millimeters, SCALING FACTOR 10 => precip_mm = code/10
                         9999=Missing
        condition code: 1位 (1=无法测量/不准, 2=Trace, 3/4=累计段起止, 5=删除段开始 ...)
        quality code: 1位
        口径：AA1 整段缺失 => precip_mm=NaN 且 precip_reported=0（缺测≠无雨）；
              AA1 存在（含 depth=0）=> 按文档换算, precip_reported=1。
- REPORT_TYPE: FM-15 = METAR 例行报, FM-16 = SPECI 特报（文档 p.6 GEOPHYSICAL-REPORT-TYPE code）。
              仅这两类进入清洗输出；SOD/SOM/FM-12 等仅统计。
- obs_utc: CSV 的 DATE 列已为 UTC 时间戳（YYYY-MM-DDTHH:MM:SS），直接按 UTC 解析。
          实证346站DATE均带完整时分秒（如 2024-01-01T00:52:00），无需从REM补时刻。

用法（项目根目录运行）：
  python cleaning\02_clean_noaa.py samples   # 仅跑3个样本站（冒烟）
  python cleaning\02_clean_noaa.py full      # 全量346站 + 合并 + 统计 + 自检
"""
import os, sys, json, math, glob
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR   = os.path.join(ROOT, "data", "raw", "NOAA", "2024")
SAMP_DIR  = os.path.join(ROOT, "data", "samples", "raw", "member1", "NOAA")
META_CSV  = os.path.join(ROOT, "metadata", "noaa_full_airports_2024.csv")
OUT_DIR   = os.path.join(ROOT, "data", "cleaned", "noaa_station")
OUT_MAIN  = os.path.join(ROOT, "data", "cleaned", "noaa_obs_2024.parquet")
STATS_JSON = os.path.join(ROOT, "data", "cleaned", "noaa_clean_stats.json")
LOG_DIR   = os.path.join(ROOT, "cleaning", "logs")
FULL_LOG  = os.path.join(LOG_DIR, "noaa_full_run.log")
FINAL_TXT = os.path.join(LOG_DIR, "noaa_final_check.txt")

MPS_TO_KTS = 1.94384449244   # 1 m/s = 1.943844 knots (METAR风速单位)

KEEP_COLS = ["STATION", "DATE", "REPORT_TYPE", "WND", "VIS", "TMP", "DEW", "SLP", "AA1", "REM"]
OUT_COLS = ["station_id","obs_utc","report_type",
            "temp_c","temp_q","dew_c","dew_q",
            "slp_hpa","slp_q",
            "wind_dir_deg","wind_dir_q","wind_speed_kts","wind_speed_q",
            "vis_m","vis_q",
            "precip_mm","precip_q","precip_period_h","precip_reported"]

FM_TYPES = {"FM-15", "FM-16"}


def split_group(v):
    """把 '220,1,N,0026,1' 切成 ['220','1','N','0026','1']；空/NaN 返回 []。"""
    if v is None: return []
    s = str(v).strip()
    if s == "" or s.lower() == "nan": return []
    return [x.strip() for x in s.split(",")]


def parse_signed_code(code, missing="+9999", scale=10.0):
    """有符号码值 -> float；缺失码或非法 -> np.nan。"""
    if code is None: return np.nan
    c = str(code).strip()
    if c == "" or c.upper() == "NAN" or c == missing: return np.nan
    try:
        return int(c) / scale
    except ValueError:
        return np.nan


def parse_unsigned_code(code, missing="99999", scale=1.0):
    if code is None: return np.nan
    c = str(code).strip()
    if c == "" or c.upper() == "NAN" or c == missing: return np.nan
    try:
        return int(c) / scale
    except ValueError:
        return np.nan


def clean_station_df(df, station_id_expected):
    """对单站 DataFrame 执行解析，返回 (cleaned_df, stats_dict)。"""
    # 兜底：列可能缺失（不同站列数不同），补空列
    for c in KEEP_COLS:
        if c not in df.columns:
            df[c] = np.nan

    n_raw = len(df)
    rt_raw = df["REPORT_TYPE"].fillna("").astype(str).str.strip()
    rtype_counts = rt_raw.value_counts(dropna=False).to_dict()
    rtype_counts = {str(k): int(v) for k, v in rtype_counts.items()}

    # 仅保留 FM-15 / FM-16（去空格后比较）
    mask = rt_raw.isin(FM_TYPES)
    df = df.loc[mask].copy()
    rt_keep = rt_raw.loc[mask]
    n_keep_type = len(df)

    # station_id：STATION 原值字符串，按清单 station_id 长度补齐前导零
    sid = df["STATION"].astype(str).str.strip().str.zfill(len(station_id_expected))

    # obs_utc：DATE 已是 UTC 时间戳
    obs_utc = pd.to_datetime(df["DATE"], utc=True, errors="coerce")
    n_bad_date = int(obs_utc.isna().sum())

    out = pd.DataFrame(index=df.index)
    out["station_id"] = sid.values
    out["obs_utc"] = obs_utc.values
    out["report_type"] = rt_keep.values

    # ---- TMP ----
    tmp_parts = df["TMP"].apply(split_group)
    out["temp_c"] = [parse_signed_code(p[0]) if len(p) >= 1 else np.nan for p in tmp_parts]
    out["temp_q"] = [p[1] if len(p) >= 2 else np.nan for p in tmp_parts]

    # ---- DEW ----
    dew_parts = df["DEW"].apply(split_group)
    out["dew_c"] = [parse_signed_code(p[0]) if len(p) >= 1 else np.nan for p in dew_parts]
    out["dew_q"] = [p[1] if len(p) >= 2 else np.nan for p in dew_parts]

    # ---- SLP (5位无符号, 99999缺失) ----
    slp_parts = df["SLP"].apply(split_group)
    out["slp_hpa"] = [parse_unsigned_code(p[0], missing="99999", scale=10.0) if len(p) >= 1 else np.nan for p in slp_parts]
    out["slp_q"] = [p[1] if len(p) >= 2 else np.nan for p in slp_parts]

    # ---- WND: dir(3,999缺失), dir_q, type, speed(4,9999缺失,m/s), speed_q ----
    wnd_parts = df["WND"].apply(split_group)
    wdir, wdir_q, wspd_kts, wspd_q = [], [], [], []
    for p in wnd_parts:
        if len(p) >= 1 and p[0] not in ("", "999"):
            try: wdir.append(int(p[0]))
            except ValueError: wdir.append(np.nan)
        else:
            wdir.append(np.nan)
        wdir_q.append(p[1] if len(p) >= 2 else np.nan)
        if len(p) >= 4 and p[3] not in ("", "9999"):
            try: wspd_kts.append(int(p[3])/10.0 * MPS_TO_KTS)
            except ValueError: wspd_kts.append(np.nan)
        else:
            wspd_kts.append(np.nan)
        wspd_q.append(p[4] if len(p) >= 5 else np.nan)
    out["wind_dir_deg"] = wdir
    out["wind_dir_q"] = wdir_q
    out["wind_speed_kts"] = wspd_kts
    out["wind_speed_q"] = wspd_q

    # ---- VIS: dist(6,米,999999缺失), dist_q, variability, var_q ----
    vis_parts = df["VIS"].apply(split_group)
    vism, visq = [], []
    for p in vis_parts:
        if len(p) >= 1 and p[0] not in ("", "999999"):
            try:
                v = int(p[0])
                if v > 160000:   # 文档: >160000 记为 160000
                    v = 160000
                vism.append(v)
            except ValueError:
                vism.append(np.nan)
        else:
            vism.append(np.nan)
        visq.append(p[1] if len(p) >= 2 else np.nan)
    out["vis_m"] = vism
    out["vis_q"] = visq

    # ---- AA1: period(2,h,99缺失), depth(4,mm,9999缺失), condition(1), q(1) ----
    aa_parts = df["AA1"].apply(split_group)
    pm, pq, pp, prep = [], [], [], []
    for p in aa_parts:
        if len(p) == 0:
            # 缺测 ≠ 无雨
            pm.append(np.nan); pq.append(np.nan); pp.append(np.nan); prep.append(0)
        else:
            prep.append(1)
            # period
            if len(p) >= 1 and p[0] not in ("", "99"):
                try: pp.append(int(p[0]))
                except ValueError: pp.append(np.nan)
            else:
                pp.append(np.nan)
            # depth (mm = code/10, 9999缺失)
            if len(p) >= 2 and p[1] not in ("", "9999"):
                try: pm.append(int(p[1])/10.0)
                except ValueError: pm.append(np.nan)
            else:
                pm.append(np.nan)
            # quality code (AA1组最后1位)
            pq.append(p[-1] if len(p) >= 3 else np.nan)
    out["precip_mm"] = pm
    out["precip_q"] = pq
    out["precip_period_h"] = pp
    out["precip_reported"] = prep

    # ---- 去重: (station_id, obs_utc, report_type) 保留首条 ----
    n_before_dedup = len(out)
    out = out.drop_duplicates(subset=["station_id","obs_utc","report_type"], keep="first")
    n_dup = n_before_dedup - len(out)

    out = out[OUT_COLS].reset_index(drop=True)
    stats = {
        "n_raw": int(n_raw),
        "rtype_counts": rtype_counts,
        "n_after_type_filter": int(n_keep_type),
        "n_bad_date": int(n_bad_date),
        "n_after_dedup": int(len(out)),
        "n_duplicates_removed": int(n_dup),
    }
    return out, stats


def load_station(path):
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False,
                       usecols=lambda c: c in KEEP_COLS)


def official_station_ids():
    m = pd.read_csv(META_CSV, dtype=str, encoding="utf-8-sig")
    return [s.strip() for s in m["station_id"].tolist()]


def run_samples():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = ["72295023174.csv", "72530094846.csv", "74486094789.csv"]
    total_raw = total_out = 0
    for fn in files:
        path = os.path.join(SAMP_DIR, fn)
        sid = fn.replace(".csv","")
        df = load_station(path)
        out, st = clean_station_df(df, sid)
        total_raw += st["n_raw"]; total_out += len(out)
        print(f"[{sid}] raw={st['n_raw']} type_filt={st['n_after_type_filter']} "
              f"bad_date={st['n_bad_date']} dedup={st['n_after_dedup']} "
              f"dup_rm={st['n_duplicates_removed']} rtypes={st['rtype_counts']}")
        print(out.head(3).to_string())
    print(f"TOTAL samples raw={total_raw} cleaned={total_out}")


def run_full():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    sids = official_station_ids()
    print(f"正式清单站点数: {len(sids)}")

    per_station = []
    log_lines = []
    total_raw = total_filt = total_dedup = total_dup = 0
    rtype_global = {}
    processed = 0
    missing_files = []
    skipped_sgu = []

    for sid in sids:
        # SGU 试采集文件 72475423186 不在正式清单，本循环不会触及；
        # 这里再显式确认一次并记录。
        path = os.path.join(RAW_DIR, f"{sid}.csv")
        if not os.path.exists(path):
            missing_files.append(sid)
            log_lines.append(f"[MISSING] {sid}: 文件不存在")
            print(f"[MISSING] {sid}")
            continue
        try:
            df = load_station(path)
            out, st = clean_station_df(df, sid)
        except Exception as e:
            log_lines.append(f"[ERROR] {sid}: {type(e).__name__}: {e}")
            print(f"[ERROR] {sid}: {e}")
            continue

        out.to_parquet(os.path.join(OUT_DIR, f"{sid}.parquet"), index=False, engine="pyarrow")

        per_station.append({"station_id": sid, **st})
        total_raw += st["n_raw"]
        total_filt += st["n_after_type_filter"]
        total_dedup += st["n_after_dedup"]
        total_dup += st["n_duplicates_removed"]
        for k, v in st["rtype_counts"].items():
            rtype_global[k] = rtype_global.get(k, 0) + v
        processed += 1
        if processed % 20 == 0 or processed == len(sids):
            print(f"进度 {processed}/{len(sids)}  当前 {sid}  cleaned={len(out)}")

    # SGU 确认
    sgu_path = os.path.join(RAW_DIR, "72475423186.csv")
    if os.path.exists(sgu_path) and "72475423186" not in sids:
        skipped_sgu.append("72475423186")
        log_lines.append("[SKIP] SGU试采集 72475423186 不在正式清单，未处理（按任务要求跳过）")

    log_lines.append("")
    log_lines.append(f"处理站点数(成功): {processed}")
    log_lines.append(f"缺失文件数: {len(missing_files)} -> {missing_files}")
    log_lines.append(f"SGU跳过: {skipped_sgu}")
    log_lines.append(f"总原始观测行数(所有报告类型): {total_raw}")
    log_lines.append(f"FM-15/FM-16过滤后行数: {total_filt}")
    log_lines.append(f"去重后行数(=各站parquet行数之和): {total_dedup}")
    log_lines.append(f"去重删除行数: {total_dup}")
    log_lines.append("全局报告类型计数:")
    for k, v in sorted(rtype_global.items(), key=lambda x: -x[1]):
        log_lines.append(f"  {k}: {v}")

    # ---- 合并所有站 parquet ----
    print("合并 parquet ...")
    pq_files = sorted(glob.glob(os.path.join(OUT_DIR, "*.parquet")))
    parts = [pd.read_parquet(p) for p in pq_files]
    merged = pd.concat(parts, ignore_index=True)
    merged.to_parquet(OUT_MAIN, index=False, engine="pyarrow")
    n_merged = len(merged)
    log_lines.append("")
    log_lines.append(f"合并parquet文件数: {len(pq_files)}")
    log_lines.append(f"合并后总行数: {n_merged}")
    log_lines.append(f"各站parquet行数之和: {total_dedup}")
    log_lines.append(f"行数一致: {n_merged == total_dedup}")

    # ---- 统计 JSON ----
    n_fm15 = rtype_global.get("FM-15", 0)
    n_fm16 = rtype_global.get("FM-16", 0)
    # 缺失率（基于清洗后 FM-15/16 去重数据 merged）
    def miss_rate(col):
        return float(merged[col].isna().mean()) if col in merged.columns else None
    stats_out = {
        "station_count": int(processed),
        "official_list_size": int(len(sids)),
        "missing_files": missing_files,
        "skipped_sgu": skipped_sgu,
        "n_raw_all_report_types": int(total_raw),
        "n_after_type_filter_fm15_fm16": int(total_filt),
        "n_fm15_raw": int(n_fm15),
        "n_fm16_raw": int(n_fm16),
        "n_duplicates_removed": int(total_dup),
        "n_cleaned_final": int(n_merged),
        "rtype_counts_global": rtype_global,
        "missing_rate": {
            "temp_c": miss_rate("temp_c"),
            "dew_c": miss_rate("dew_c"),
            "slp_hpa": miss_rate("slp_hpa"),
            "wind_dir_deg": miss_rate("wind_dir_deg"),
            "wind_speed_kts": miss_rate("wind_speed_kts"),
            "vis_m": miss_rate("vis_m"),
            "precip_mm": miss_rate("precip_mm"),
        },
        "quality_code_dist": {
            "temp_q": merged["temp_q"].value_counts(dropna=False).to_dict(),
            "dew_q": merged["dew_q"].value_counts(dropna=False).to_dict(),
            "slp_q": merged["slp_q"].value_counts(dropna=False).to_dict(),
            "wind_speed_q": merged["wind_speed_q"].value_counts(dropna=False).to_dict(),
            "vis_q": merged["vis_q"].value_counts(dropna=False).to_dict(),
            "precip_q": merged["precip_q"].value_counts(dropna=False).to_dict(),
        },
        "per_station": per_station,
    }
    # value_counts 的 key 可能是 np.nan -> 转 str 以便 JSON 序列化
    def _keys_to_str(o):
        if isinstance(o, dict):
            return {str(k): _keys_to_str(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_keys_to_str(x) for x in o]
        return o
    stats_out = _keys_to_str(stats_out)
    with open(STATS_JSON, "w", encoding="utf-8") as f:
        json.dump(stats_out, f, ensure_ascii=False, indent=2)
    log_lines.append(f"统计JSON已写: {STATS_JSON}")

    # ---- 最终自检：重读合并parquet ----
    chk = pd.read_parquet(OUT_MAIN)
    final_lines = []
    final_lines.append(f"重读合并parquet: {OUT_MAIN}")
    final_lines.append(f"行数: {len(chk)}")
    final_lines.append(f"列数: {len(chk.columns)}")
    final_lines.append(f"列名: {list(chk.columns)}")
    final_lines.append("")
    final_lines.append("核心列非空率:")
    for c in ["obs_utc","temp_c","dew_c","slp_hpa","wind_dir_deg","wind_speed_kts","vis_m","precip_mm","precip_reported"]:
        nn = chk[c].notna().sum()
        final_lines.append(f"  {c}: 非空 {nn}/{len(chk)} ({nn/len(chk)*100:.2f}%)")
    final_lines.append("")
    final_lines.append("report_type 分布:")
    for k, v in chk["report_type"].value_counts(dropna=False).items():
        final_lines.append(f"  {k}: {v}")
    final_lines.append("")
    final_lines.append("station_id 唯一数: " + str(chk['station_id'].nunique()))
    final_lines.append("obs_utc 范围: " + str(chk['obs_utc'].min()) + " ~ " + str(chk['obs_utc'].max()))
    final_lines.append("")
    final_lines.append("样例前5行:")
    final_lines.append(chk.head(5).to_string())
    with open(FINAL_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(final_lines) + "\n")
    print("\n".join(final_lines))

    with open(FULL_LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    print(f"\n全量完成。日志: {FULL_LOG}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "samples"
    if mode == "samples":
        run_samples()
    elif mode == "full":
        run_full()
    else:
        print("用法: python cleaning\\02_clean_noaa.py [samples|full]")
