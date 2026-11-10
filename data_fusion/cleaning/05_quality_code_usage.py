# -*- coding: utf-8 -*-
"""
05_quality_code_usage.py — 把融合主表 matched 子集的四要素 ISD 质量码批量归类，
供后续分析（成员3/4/5）统一数据使用规则。

只读 data/integrated/flights_weather_2024.parquet（仅 weather_match_status=='matched' 子集）。

ISD 单字符质量码分类（依据官方 ISD Format Document，
https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf）：
  可用 usable      : 0=通过粗范围  1=通过全部质控  4=粗范围(NCEI源) 5=全部质控(NCEI源)
                     C=人工核查  A=标可疑但接受为可用
  不确定 uncertain : 2=可疑  6=可疑(NCEI源)  M=NWS/FAA人工改值
                     I=验证器补插(非原始)  P=验证器替换  R=NCEI软件算得替换  U=编辑后替换
  不可用 erroneous : 3=错误  7=错误(NCEI源)
  缺测 missing     : 9=缺测  以及 q 为空/NaN（对应数值列通常也为 NaN）

口径：归类只看质量码；"缺测"与数值列为 NaN 互为印证。不可只凭天气数值非空认定有效。

输出：
  data/integrated/quality_code_usage_stats.json
  cleaning/logs/quality_code_usage.txt
用法（项目根目录）：python cleaning\\05_quality_code_usage.py
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "data" / "integrated" / "quality_code_usage_stats.json"
OUT_TXT = ROOT / "cleaning" / "logs" / "quality_code_usage.txt"

USABLE = {"0", "1", "4", "5", "C", "A"}
UNCERTAIN = {"2", "6", "M", "I", "P", "R", "U"}
UNUSABLE = {"3", "7"}
MISSING = {"9"}

ELEMENTS = {
    "temp": ("temp_c", "temp_q"),
    "vis": ("vis_m", "vis_q"),
    "wind_speed": ("wind_speed_kts", "wind_speed_q"),
    "precip": ("precip_mm", "precip_q"),
}


def classify(q) -> str:
    if q is None:
        return "missing"
    s = str(q).strip()
    if s == "" or s.lower() == "nan":
        return "missing"
    if s in USABLE:
        return "usable"
    if s in UNCERTAIN:
        return "uncertain"
    if s in UNUSABLE:
        return "erroneous"
    if s in MISSING:
        return "missing"
    return "other"


def main():
    cols = ["weather_match_status",
            "temp_c", "temp_q", "vis_m", "vis_q",
            "wind_speed_kts", "wind_speed_q",
            "precip_mm", "precip_q", "precip_period_h", "precip_reported"]
    df = pd.read_parquet(ROOT / "data" / "integrated" / "flights_weather_2024.parquet",
                         columns=cols)
    matched = df[df["weather_match_status"] == "matched"].copy()
    n = len(matched)

    stats = {"matched_rows": int(n), "elements": {}, "precip_period_h": {}}
    lines = []
    lines.append("=" * 70)
    lines.append("质量码归类统计（仅 weather_match_status=='matched' 子集）")
    lines.append(f"matched 行数: {n}")
    lines.append("分类依据: ISD Format Document（见脚本头注释）")
    lines.append("=" * 70)

    for name, (val_col, q_col) in ELEMENTS.items():
        bucket = matched[q_col].map(classify)
        vc = bucket.value_counts()
        counts = {b: int(vc.get(b, 0)) for b in
                  ["usable", "uncertain", "erroneous", "missing", "other"]}
        pct = {b: round(100.0 * c / n, 3) for b, c in counts.items()}
        qcode_vc = matched[q_col].astype(str).str.strip().value_counts()
        stats["elements"][name] = {
            "value_column": val_col, "q_column": q_col,
            "bucket_counts": counts, "bucket_pct": pct,
            "usable_pct": pct["usable"],
            "uncertain_pct": pct["uncertain"],
            "erroneous_pct": pct["erroneous"],
            "missing_pct": pct["missing"],
            "raw_qcode_counts": {str(k): int(v) for k, v in qcode_vc.items()},
            "value_nan_count": int(matched[val_col].isna().sum()),
        }
        lines.append("")
        lines.append(f"--- {name} ({q_col}) ---")
        lines.append(f"  可用 usable   : {counts['usable']:>8} ({pct['usable']:.3f}%)")
        lines.append(f"  不确定 uncertain: {counts['uncertain']:>8} ({pct['uncertain']:.3f}%)")
        lines.append(f"  不可用 erroneous : {counts['erroneous']:>8} ({pct['erroneous']:.3f}%)")
        lines.append(f"  缺测 missing    : {counts['missing']:>8} ({pct['missing']:.3f}%)")
        if counts["other"]:
            lines.append(f"  未分类 other    : {counts['other']:>8} ({pct['other']:.3f}%)  codes={list(qcode_vc.index)}")
        lines.append(f"  原始数值 NaN 行数: {counts['missing'] and int(matched[val_col].isna().sum())}")

    # precip_period_h 分布（matched 子集）
    pp = matched["precip_period_h"]
    pp_vc = pp.value_counts(dropna=False).sort_index()
    pp_dict = {("NaN" if pd.isna(k) else str(int(k))): int(v) for k, v in pp_vc.items()}
    stats["precip_period_h"] = {"distribution": pp_dict,
                                 "note": "主分析只用 precip_period_h==1（1小时累计）；不得与3/6/24小时累计混作同一小时降水量"}
    lines.append("")
    lines.append("--- precip_period_h 分布（matched 子集）---")
    for k, v in pp_dict.items():
        lines.append(f"  period={k:>4} h : {v:>8} ({100.0*v/n:.3f}%)")

    # 主分析可用降水：matched & precip_reported==1 & period==1
    p1 = matched[(matched["precip_reported"] == 1) & (matched["precip_period_h"] == 1)]
    stats["precip_main_analyzable_rows"] = int(len(p1))
    lines.append("")
    lines.append(f"主分析降水可用行（matched & precip_reported==1 & period==1h）: {len(p1)} ({100.0*len(p1)/n:.3f}%)")

    OUT_JSON.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[written] {OUT_JSON}")
    print(f"[written] {OUT_TXT}")


if __name__ == "__main__":
    main()
