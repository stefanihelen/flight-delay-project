# -*- coding: utf-8 -*-
"""样本站 REM(METAR原文) 交叉核验：抽>=10条，逐条对照解析值与METAR报文。

对齐方式：用 (station_id, obs_utc) 合并清洗结果与原始FM-15/16行，
避免去重导致位置错位。
对照容差：TMP/DEW ±0.6℃（METAR整度报）、风速 ±1.5kt、VIS ±100m、SLP ±0.2hPa。
规则来源：ISD Format Document（见 02_clean_noaa.py 注释）。
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
from importlib import import_module
m = import_module("02_clean_noaa")

ROOT = m.ROOT
SAMP_DIR = m.SAMP_DIR
OUT = os.path.join(m.LOG_DIR, "noaa_sample_verify.txt")


def parse_metar(rem):
    """从REM文本中提取METAR正文明细。返回dict。

    REM格式: "MET09912/31/23 19:52:03 METAR KATL ..."
             "MET12301/09/24 12:13:02 SPECI KORD ..."
    必须从 " METAR " 或 " SPECI " 关键字后开始，否则前缀日期 MM/DD/YY
    里的斜杠会被温露正则误匹配。
    """
    if not isinstance(rem, str): return {}
    # 定位 METAR 或 SPECI 报文主体起点
    m = re.search(r"\b(METAR|SPECI)\b", rem)
    body = rem[m.start():] if m else rem
    # 去掉 RMK 之后内容
    body = re.split(r"\sRMK\s", body)[0]
    res = {}
    # 风 22005KT / VRB03KT / 22005G17KT
    w = re.search(r"\d{3}(\d{2,3})(?:G\d{2,3})?KT", body)
    wd = re.search(r"\b(\d{3})(\d{2,3})(?:G\d{2,3})?KT\b", body)
    if wd:
        res["met_wdir"] = int(wd.group(1)); res["met_wspd_kts"] = int(wd.group(2))
    elif "VRB" in body:
        wv = re.search(r"VRB(\d{2,3})(?:G\d{2,3})?KT", body)
        if wv:
            res["met_wspd_kts"] = int(wv.group(1)); res["met_wdir_vrb"] = True
    # 能见度：先匹配带分数 "1 1/2SM"，再分数 "1/2SM"，再整数 "10SM"
    v_mixed = re.search(r"\b(\d+)\s+(\d+)/(\d+)SM\b", body)
    v_frac  = re.search(r"\bM?(\d+)/(\d+)SM\b", body)
    v_whole = re.search(r"\bM?(\d+)SM\b", body)
    if v_mixed:
        sm = int(v_mixed.group(1)) + int(v_mixed.group(2))/int(v_mixed.group(3))
    elif v_frac:
        sm = int(v_frac.group(1))/int(v_frac.group(2))
    elif v_whole:
        sm = int(v_whole.group(1))
    else:
        sm = None
    if sm is not None:
        res["met_vis_m"] = round(sm * 1609.344)
    # 温度/露点：找形如 09/00 或 M02/M08 的 token（带词边界，避免误匹配日期）
    td = re.search(r"\b(M?\d{2})/(M?\d{2})\b", body)
    if td:
        def cv(s): return -int(s[1:]) if s.startswith("M") else int(s)
        res["met_temp_c"] = cv(td.group(1)); res["met_dew_c"] = cv(td.group(2))
    # 修正海平面气压 SLPddd
    sl = re.search(r"SLP(\d{3})", body)
    if sl:
        d = sl.group(1)
        v = int(d) / 10.0
        res["met_slp_hpa"] = (v + 1000) if v < 500 else (v + 900)
    res["body"] = body.strip()
    return res


def main():
    os.makedirs(m.LOG_DIR, exist_ok=True)
    files = ["72295023174.csv", "72530094846.csv", "74486094789.csv"]
    rows_out = []
    checked = 0; agree = 0
    per_station = {}

    for fn in files:
        sid = fn.replace(".csv", "")
        raw = m.load_station(os.path.join(SAMP_DIR, fn))
        clean, st = m.clean_station_df(raw, sid)
        # 原始 FM-15/16 行（带 REM）
        raw["_rt"] = raw["REPORT_TYPE"].fillna("").astype(str).str.strip()
        fm = raw[raw["_rt"].isin(["FM-15", "FM-16"])].copy()
        # clean.obs_utc 来自 pd.to_datetime(utc=True).values，tz已剥为naive UTC；
        # 这里也用naive解析以对齐
        fm["_dt"] = pd.to_datetime(fm["DATE"], errors="coerce")
        # 用 (station_id, obs_utc) 与 clean 对齐
        merged = clean.merge(
            fm[["STATION", "_dt", "REM"]],
            left_on=["station_id", "obs_utc"],
            right_on=["STATION", "_dt"],
            how="left"
        )
        per_station[sid] = {"clean": int(len(clean)), "fm_raw": int(len(fm)), "matched": int(merged["REM"].notna().sum())}
        # 等间隔抽样，每站约5条（总计>=10）
        n = len(merged)
        if n == 0: continue
        idxs = list(range(0, n, max(1, n // 5)))[:5]
        for ix in idxs:
            r = merged.iloc[ix]
            rem = r["REM"]
            met = parse_metar(rem)
            checked += 1
            lines = []
            lines.append(f"--- 第{checked}条 | 站 {sid} | {r['obs_utc']} UTC | {r['report_type']} ---")
            lines.append(f"METAR原文: {met.get('body','(无REM)')}")
            ok_all = True
            used_any = False
            # TMP
            if "met_temp_c" in met and pd.notna(r['temp_c']):
                used_any = True
                ok = abs(r['temp_c'] - met['met_temp_c']) <= 0.6
                ok_all &= ok
                lines.append(f"  温度:   解析={r['temp_c']:.1f}C  METAR={met['met_temp_c']}C  -> {'一致' if ok else '偏差'}")
            # DEW
            if "met_dew_c" in met and pd.notna(r['dew_c']):
                used_any = True
                ok = abs(r['dew_c'] - met['met_dew_c']) <= 0.6
                ok_all &= ok
                lines.append(f"  露点:   解析={r['dew_c']:.1f}C  METAR={met['met_dew_c']}C  -> {'一致' if ok else '偏差'}")
            # WIND
            if "met_wspd_kts" in met and pd.notna(r['wind_speed_kts']):
                used_any = True
                ok_spd = abs(r['wind_speed_kts'] - met['met_wspd_kts']) <= 1.5
                ok_dir = True
                if not met.get("met_wdir_vrb") and "met_wdir" in met and pd.notna(r['wind_dir_deg']):
                    ok_dir = (int(r['wind_dir_deg']) == met['met_wdir'])
                ok = ok_spd and ok_dir
                ok_all &= ok
                lines.append(f"  风:     解析=({r['wind_dir_deg']:.0f}deg,{r['wind_speed_kts']:.1f}kt)  METAR=({met.get('met_wdir','VRB')},{met['met_wspd_kts']}kt)  -> {'一致' if ok else '偏差'}")
            # VIS
            if "met_vis_m" in met and pd.notna(r['vis_m']):
                used_any = True
                ok = abs(r['vis_m'] - met['met_vis_m']) <= 100
                ok_all &= ok
                lines.append(f"  能见度: 解析={r['vis_m']}m  METAR={met['met_vis_m']}m  -> {'一致' if ok else '偏差'}")
            # SLP
            if "met_slp_hpa" in met and pd.notna(r['slp_hpa']):
                used_any = True
                ok = abs(r['slp_hpa'] - met['met_slp_hpa']) <= 0.2
                ok_all &= ok
                lines.append(f"  气压:   解析={r['slp_hpa']:.1f}hPa  METAR={met['met_slp_hpa']:.1f}hPa  -> {'一致' if ok else '偏差'}")
            if used_any:
                lines.append(f"  综合:   {'一致' if ok_all else '存在偏差(见上)'}")
                if ok_all: agree += 1
            else:
                lines.append("  综合:   METAR无可对照字段")
            rows_out.append("\n".join(lines))

    header = (
        f"样本交叉核验：共抽 {checked} 条，{agree} 条全部一致，{checked-agree} 条有偏差。\n"
        f"对照口径：TMP/DEW 允许±0.6C(METAR整度)；风速 knot 允许±1.5；VIS米±100；SLP±0.2hPa。\n"
        f"规则来源：ISD Format Document（见02_clean_noaa.py注释）。\n"
        f"各站对齐情况: " + json_dumps(per_station) + "\n"
        + "="*70 + "\n"
    )
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(rows_out) + "\n")
    print(header)
    print("\n".join(rows_out))


def json_dumps(o):
    import json
    return json.dumps(o, ensure_ascii=False)


if __name__ == "__main__":
    main()
