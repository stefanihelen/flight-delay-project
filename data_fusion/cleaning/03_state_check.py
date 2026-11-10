# -*- coding: utf-8 -*-
"""
03_state_check.py
子任务：Census 2024 州界 point-in-polygon 核验

输入（只读）：
  data/cleaned/airport_timezones.csv        上一步产物（348 机场坐标）
  metadata/bts_airports_2024.csv            BTS state 列
  data/raw/Census/cb_2024_us_state_500k.zip NAD83 州界
  metadata/census_states_2024.csv           STUSPS/NAME 参考

输出（新增）：
  data/cleaned/airport_state_check.csv
列：airport_code, bts_airport_id, lat, lon, polygon_state, polygon_state_name,
    bts_state, state_consistent(1/0/na), note

临时目录：data/cleaned/_census_tmp_03/ （脚本末尾删除）
坐标系：州界 NAD83 十进制度、机场坐标 WGS84 十进制度；500k 比例尺下偏差 <1m，
       未做投影/坐标转换，近似按同一经纬度处理（在 note 与日志中注明）。
"""
from __future__ import annotations
import json, shutil, zipfile
from pathlib import Path
import pandas as pd
import shapefile  # pyshp
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
CENSUS_ZIP = ROOT / "data" / "raw" / "Census" / "cb_2024_us_state_500k.zip"
TMP = ROOT / "data" / "cleaned" / "_census_tmp_03"
OUTDIR = ROOT / "data" / "cleaned"
LOGDIR = ROOT / "cleaning" / "logs"
LOGDIR.mkdir(parents=True, exist_ok=True)

# ---------- 1. 解压到自己的临时目录 ----------
if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir(parents=True)
with zipfile.ZipFile(CENSUS_ZIP) as z:
    z.extractall(TMP)
shp_files = list(TMP.glob("*.shp"))
assert len(shp_files) == 1, f"expected 1 shp, got {shp_files}"
shp_path = shp_files[0].with_suffix("")
print(f"[unzip] -> {TMP}")

# ---------- 2. 读 SHP，构建 shapely 几何 ----------
r = shapefile.Reader(str(shp_path))
fields = [f[0] for f in r.fields[1:]]
print(f"[shp] fields={fields} n_records={len(r)}")
geoms = []
meta = []
for sr in r.iterShapeRecords():
    rec = sr.record.as_dict()
    gj = sr.shape.__geo_interface__
    g = shape(gj)
    geoms.append(g)
    meta.append({"STUSPS": rec.get("STUSPS"), "NAME": rec.get("NAME"),
                 "STATEFP": rec.get("STATEFP")})
r.close()  # 释放 SHP/SHX/DBF/CPG 文件句柄，便于 Windows 下 rmtree
print(f"[shp] built {len(geoms)} polygons")

# ---------- 3. 读机场坐标表 ----------
tz = pd.read_csv(OUTDIR / "airport_timezones.csv", dtype={"bts_airport_id": str})
bts = pd.read_csv(ROOT / "metadata" / "bts_airports_2024.csv", dtype=str)
bts_state = dict(zip(bts.airport_code, bts.state))
print(f"[read] timezones rows={len(tz)}, bts rows={len(bts)}")

# ---------- 4. 逐机场 point-in-polygon ----------
# 用 STRtree 加速；先粗筛候选多边形，再 contains 判定
tree = STRtree(geoms)

def classify(lat, lon):
    if pd.isna(lat) or pd.isna(lon):
        return None, None, "no_coord"
    pt = Point(float(lon), float(lat))
    # 候选：与 pt 距离 <=0.5 度（约55km）内的多边形
    cand = tree.query(pt, predicate="dwithin", distance=0.5)
    hits = []
    for idx in cand:
        g = geoms[idx]
        if g.contains(pt) or g.touches(pt):
            hits.append(idx)
    if len(hits) == 1:
        return meta[hits[0]]["STUSPS"], meta[hits[0]]["NAME"], "inside"
    if len(hits) > 1:
        # 重叠多边形少见；取第一个
        return (meta[hits[0]]["STUSPS"], meta[hits[0]]["NAME"],
                f"multi_polygon_hit({len(hits)})")
    # 未命中：找最近多边形报告距离
    nearest = tree.nearest(pt)
    g = geoms[nearest]
    d = g.distance(pt)
    return meta[nearest]["STUSPS"], meta[nearest]["NAME"], f"outside_closest_{d:.4f}deg"

results = []
for _, row in tz.iterrows():
    code = row.airport_code; aid = row.bts_airport_id
    lat = row.lat; lon = row.lon
    poly_st, poly_name, how = classify(lat, lon)
    bts_st = bts_state.get(code, "")
    note_parts = [f"how={how}", "crs=NAD83/WGS84近似未投影"]
    consistent = "na"
    if poly_st is None:
        consistent = "na"
        note_parts.append("no_coordinates")
    elif bts_st == "TT":
        # BTS 地区聚合码 TT 用于海外领地（GUM=关岛, PPG=美属萨摩亚, SPN=北马里亚纳）
        # Census 形状文件里分别有 GU/AS/MP 独立多边形；这是编码体系差异，不是真实位置错误
        consistent = "na"
        note_parts.append(
            f"BTS_TT_territory_code;polygon={poly_st}({poly_name});known_encoding_diff")
    elif how == "inside":
        if bts_st == poly_st:
            consistent = "1"
        else:
            consistent = "0"
            note_parts.append(f"bts={bts_st} vs polygon={poly_st}")
    else:
        # outside / boundary / territory edge
        if bts_st == poly_st:
            consistent = "1"
            note_parts.append("boundary_edge_but_code_match")
        else:
            consistent = "0"
            note_parts.append(f"boundary/territory_mismatch bts={bts_st} nearest_poly={poly_st}")
    results.append({
        "airport_code": code, "bts_airport_id": aid,
        "lat": lat, "lon": lon,
        "polygon_state": poly_st or "",
        "polygon_state_name": poly_name or "",
        "bts_state": bts_st,
        "state_consistent": consistent,
        "note": ";".join(note_parts),
    })

out = pd.DataFrame(results)
out.to_csv(OUTDIR / "airport_state_check.csv", index=False, encoding="utf-8")

# ---------- 5. 统计 ----------
n = len(out)
n_inside = (out.note.str.contains("how=inside")).sum()
n_boundary = out.state_consistent.isin(["0"]).sum()
n_match = (out.state_consistent == "1").sum()
n_mismatch = (out.state_consistent == "0").sum()
n_na = (out.state_consistent == "na").sum()
n_tt = (out.bts_state == "TT").sum()
mismatch_list = out[out.state_consistent == "0"][
    ["airport_code", "bts_state", "polygon_state", "polygon_state_name", "note"]]

print(f"[state] n={n} inside={n_inside} match={n_match} mismatch={n_mismatch} na={n_na} TT={n_tt}")
print("--- mismatch list ---")
print(mismatch_list.to_string(index=False))

# ---------- 6. 清理临时目录 ----------
shutil.rmtree(TMP)
print(f"[cleanup] removed {TMP}")

# ---------- 7. 摘要 JSON ----------
summary = {
    "n_airports": int(n),
    "inside_polygon": int(n_inside),
    "consistent": int(n_match),
    "inconsistent": int(n_mismatch),
    "na": int(n_na),
    "bts_TT_count": int(n_tt),
    "mismatch_records": mismatch_list.to_dict(orient="records"),
}
Path(ROOT / "cleaning" / "_state_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("[done] wrote", OUTDIR / "airport_state_check.csv")
