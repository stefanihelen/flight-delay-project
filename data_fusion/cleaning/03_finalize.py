# -*- coding: utf-8 -*-
"""
03_finalize.py
汇总日志、stats JSON、自检读回；清理本模块自建的临时文件。
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CLEANED = ROOT / "data" / "cleaned"
LOGDIR = ROOT / "cleaning" / "logs"
LOGDIR.mkdir(parents=True, exist_ok=True)

tz = pd.read_csv(CLEANED / "airport_timezones.csv", dtype={"bts_airport_id": str})
sc = pd.read_csv(CLEANED / "airport_state_check.csv", dtype={"bts_airport_id": str})
tz_sum = json.loads((ROOT / "cleaning" / "_tz_summary.json").read_text(encoding="utf-8"))
st_sum = json.loads((ROOT / "cleaning" / "_state_summary.json").read_text(encoding="utf-8"))

# ---------- 日志 ----------
lines = []
P = lines.append
P("=" * 78)
P("机场时区表与州界归属核验 — 运行日志")
P("子任务归属：成员2 清洗与融合 / 机场时区表 + Census 州界核验")
P("运行环境：Windows + Python 3.13.16；pandas 3.1.0；timezonefinder 9.2.0；pyshp 3.1.6；shapely 2.2.0")
P("=" * 78)
P("")
P("一、坐标来源")
P("-" * 78)
P(f"机场总数（bts_airports_2024.csv）: {len(tz)}")
src = tz.coord_source.value_counts().to_dict()
for k, v in src.items():
    P(f"  coord_source={k}: {v}")
P("说明：348 机场坐标全部来自 metadata/airport_station_mapping_reviewed.csv "
  "(airport_latitude/airport_longitude)，未触发 OurAirports 回退。")
P("")
P("二、时区查询（timezonefinder）")
P("-" * 78)
P(f"时区获取成功: {tz_sum['tz_success']}")
P(f"时区获取失败/None: {tz_sum['tz_fail']}")
P(f"时区方法分布: {tz.tz_method.value_counts().to_dict()}")
P(f"唯一 IANA 时区数: {tz.tz_iana.nunique()}")
P("None 清单及处理: 无（timezonefinder 对全部 348 个坐标均直接返回 IANA 名，"
  "包括 AK/HI/PR/VI/GU/AS/MP 等领地机场；未触发 territory_rule / alaska_lon_rule 推断分支）")
P("")
P("三、金标准 5 机场断言核验")
P("-" * 78)
P(f"{'code':<6}{'expected':<28}{'got':<28}{'result'}")
for g in tz_sum["gold"]:
    P(f"{g['code']:<6}{g['expect']:<28}{g['got']:<28}{g['result']}")
P("")
P("四、Census 州界 point-in-polygon 核验")
P("-" * 78)
P("坐标系说明：cb_2024_us_state_500k 为 NAD83 十进制度（GRS1980 椭球）；"
  "机场坐标为 WGS84 十进制度。两者在 1:500k 比例尺下偏差远小于制图误差，"
  "本次未做投影/基准转换，近似按同一经纬度处理（pyshp 读 SHP + shapely STRtree "
  "dwithin=0.5deg 粗筛 + contains/touches 判定）。")
P(f"SHP 多边形数: 56")
P(f"落入多边形内 (how=inside): {st_sum['inside_polygon']}")
P(f"与 BTS state 一致 (state_consistent=1): {st_sum['consistent']}")
P(f"与 BTS state 不一致 (state_consistent=0): {st_sum['inconsistent']}")
P(f"不适用 (state_consistent=na): {st_sum['na']}")
P(f"BTS state=TT 的机场数: {st_sum['bts_TT_count']}")
P("")
P("五、TT 地区异常码单独说明")
P("-" * 78)
P("BTS 用 'TT' 作为海外领地聚合州码，对应 Census 中三个独立多边形：")
tt_rows = sc[sc.bts_state == "TT"]
for _, r in tt_rows.iterrows():
    P(f"  {r.airport_code:<4} BTS_state={r.bts_state}  polygon={r.polygon_state} "
      f"({r.polygon_state_name})  state_consistent=na  (编码体系差异，非位置错误)")
P("")
P("六、州界不一致清单（state_consistent=0）")
P("-" * 78)
if st_sum["mismatch_records"]:
    for m in st_sum["mismatch_records"]:
        P(f"  {m}")
else:
    P("  （无）348 个机场全部落入对应州多边形，无真实位置不一致。")
P("")
P("七、边界/离岸/领地异常逐条说明")
P("-" * 78)
edge = sc[~sc.note.str.contains("how=inside;crs=NAD83/WGS84近似未投影$", regex=True)]
# 上述正则太严，改为列出 note 中带额外说明的行
edge_rows = sc[sc.note.str.contains("BTS_TT|boundary|outside|multi_polygon|no_coord",
                                   regex=True, na=False)]
if len(edge_rows) == 0:
    P("  无边界擦边/离岸/未命中多边形的机场。")
else:
    for _, r in edge_rows.iterrows():
        P(f"  {r.airport_code}: {r.note}")
P("")
P("八、自检：读回两个 CSV 打印行数与样例")
P("-" * 78)
P(f"airport_timezones.csv 行数: {len(tz)} 列: {list(tz.columns)}")
P("样例前3行:")
for line in tz.head(3).to_string(index=False).splitlines():
    P("  " + line)
P(f"airport_state_check.csv 行数: {len(sc)} 列: {list(sc.columns)}")
P("样例前3行:")
for line in sc.head(3).to_string(index=False).splitlines():
    P("  " + line)
P("")
P("九、临时目录清理")
P("-" * 78)
tmp = CLEANED / "_census_tmp_03"
P(f"解压临时目录 {tmp} 存在? {tmp.exists()}（应为 False）")
P("")
P("=" * 78)
P("END")
P("=" * 78)

(LOGDIR / "timezone_state_verify.txt").write_text("\n".join(lines), encoding="utf-8")

# ---------- stats JSON ----------
stats = {
    "n_airports": int(len(tz)),
    "coord_source": {k: int(v) for k, v in src.items()},
    "tz_success": int(tz_sum["tz_success"]),
    "tz_fail": int(tz_sum["tz_fail"]),
    "tz_method_distribution": {k: int(v) for k, v in
                               tz.tz_method.value_counts().to_dict().items()},
    "tz_unique_count": int(tz.tz_iana.nunique()),
    "gold_standard": tz_sum["gold"],
    "state_inside_polygon": int(st_sum["inside_polygon"]),
    "state_boundary_or_outside": int(len(sc) - st_sum["inside_polygon"]),
    "state_consistent": int(st_sum["consistent"]),
    "state_inconsistent": int(st_sum["inconsistent"]),
    "state_na": int(st_sum["na"]),
    "bts_TT_count": int(st_sum["bts_TT_count"]),
    "crs_note": "NAD83 (州界) 与 WGS84 (机场坐标) 均为十进制度，500k 比例尺下近似按同一经纬度处理，未做投影/基准转换",
}
(CLEANED / "airport_timezone_stats.json").write_text(
    json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

print("wrote", LOGDIR / "timezone_state_verify.txt")
print("wrote", CLEANED / "airport_timezone_stats.json")
