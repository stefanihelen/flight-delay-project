# -*- coding: utf-8 -*-
"""
03_airport_timezones.py
子任务：机场坐标表 + 时区表构建

输入（只读）：
  metadata/bts_airports_2024.csv            348 机场代码/AirportID 权威清单
  metadata/airport_station_mapping_reviewed.csv  修订版坐标（优先）
  data/raw/OurAirports/airports.csv         86k 机场，坐标回退源

输出（新增）：
  data/cleaned/airport_timezones.csv
列：airport_code, bts_airport_id, lat, lon, coord_source, tz_iana, tz_method, tz_note

坐标来源优先级：
  mapping_reviewed  -> ourairports_iata -> ourairports_ident -> none
时区方法：
  timezonefinder    直接由坐标查询
  nearest_infer     timezonefinder 返回 None，按邻近已知时区/属地规则推断（tz_note 写明）
"""
from __future__ import annotations
import sys, json, math
from pathlib import Path
import pandas as pd
from timezonefinder import TimezoneFinder

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "metadata"
RAW = ROOT / "data" / "raw"
OUTDIR = ROOT / "data" / "cleaned"
OUTDIR.mkdir(parents=True, exist_ok=True)

# ---------- 1. 读入权威机场清单 ----------
bts = pd.read_csv(META / "bts_airports_2024.csv", dtype=str)
bts["bts_airport_id"] = bts["bts_airport_id"].astype(str)
print(f"[read] bts_airports_2024 rows={len(bts)} cols={list(bts.columns)}")

# ---------- 2. mapping_reviewed 坐标 ----------
mp = pd.read_csv(META / "airport_station_mapping_reviewed.csv", dtype=str)
mp["bts_airport_id"] = mp["bts_airport_id"].astype(str)
print(f"[read] mapping_reviewed rows={len(mp)}")

def good(v):
    if v is None: return False
    if isinstance(v, float) and pd.isna(v): return False
    sv = str(v).strip()
    return sv not in ("", "nan", "NaN", "None")

mp_idx = {}
for _, r in mp.iterrows():
    key = (r["airport_code"], r["bts_airport_id"])
    mp_idx[key] = {
        "lat": r.get("airport_latitude"),
        "lon": r.get("airport_longitude"),
        "ident": r.get("ourairports_ident"),
    }

# ---------- 3. OurAirports 索引（iata / ident / gps_code） ----------
oa = pd.read_csv(RAW / "OurAirports" / "airports.csv", dtype=str, low_memory=False)
print(f"[read] ourairports rows={len(oa)}")

def s(v):
    if v is None: return ""
    if isinstance(v, float) and pd.isna(v): return ""
    return str(v).strip()

oa_iata = {}
oa_ident = {}
for _, r in oa.iterrows():
    iata = s(r.get("iata_code"))
    ident = s(r.get("ident"))
    gps = s(r.get("gps_code"))
    try:
        lat = float(r["latitude_deg"]); lon = float(r["longitude_deg"])
    except Exception:
        continue
    rec = {"lat": lat, "lon": lon}
    # 仅保留 US 记录，避免国外同名 IATA 干扰
    if s(r.get("iso_country")) == "US":
        if iata and iata not in oa_iata:
            oa_iata[iata] = rec
        if ident and ident not in oa_ident:
            oa_ident[ident] = rec
        if gps and gps not in oa_ident:
            oa_ident[gps] = rec

# ---------- 4. 逐机场解析坐标 ----------
rows = []
coord_counter = {}
for _, r in bts.iterrows():
    code = r["airport_code"]; aid = r["bts_airport_id"]
    lat = lon = None; src = "none"; note_parts = []

    m = mp_idx.get((code, aid))
    if m and good(m["lat"]) and good(m["lon"]):
        try:
            lat = float(m["lat"]); lon = float(m["lon"]); src = "mapping_reviewed"
        except Exception:
            m = None
    if src == "none":
        rec = oa_iata.get(code)
        if rec:
            lat, lon, src = rec["lat"], rec["lon"], "ourairports_iata"
    if src == "none":
        ident = (m or {}).get("ident") if m else None
        ident = ident or code
        rec = oa_ident.get(ident)
        if rec:
            lat, lon, src = rec["lat"], rec["lon"], "ourairports_ident"
    coord_counter[src] = coord_counter.get(src, 0) + 1
    rows.append({"airport_code": code, "bts_airport_id": aid,
                 "lat": lat, "lon": lon, "coord_source": src,
                 "bts_state": r["state"]})

df = pd.DataFrame(rows)
df["tz_iana"] = None
df["tz_method"] = ""
df["tz_note"] = ""
print("[coord_source]", coord_counter)

# ---------- 5. timezonefinder 查 IANA ----------
tf = TimezoneFinder()

def lookup_tz(lat, lon):
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return None
    try:
        return tf.timezone_at(lng=float(lon), lat=float(lat))
    except Exception:
        return None

# 属地/边界已知规则：timezonefinder 对近海/领地/边界点常返回 None
# 规则按 bts_state + 代码补充，tz_note 记录推断依据
TERRITORY_TZ = {
    "PR": "America/Puerto_Rico",     # 波多黎各
    "VI": "America/St_Thomas",       # 美属维京群岛（STT/STX）
    "HI": "Pacific/Honolulu",        # 夏威夷
}
# 阿拉斯加各时区（按经度粗分）
def alaska_tz(lon):
    # -169.5 以西 Aleutian；-137 以西 Alaska 标准；以东边境附近 Yakutat/Juneau
    if lon is None: return "America/Anchorage"
    if lon <= -168.5: return "America/Adak"
    if lon <= -141.0: return "America/Anchorage"
    if lon <= -137.5: return "America/Anchorage"   # 内陆
    return "America/Juneau"

tz_success = 0
tz_fail = 0
none_rows = []
for i, r in df.iterrows():
    tz = lookup_tz(r["lat"], r["lon"])
    method = "timezonefinder"; note = ""
    if tz is None:
        # 就近/属地推断
        st = r["bts_state"]
        if st in TERRITORY_TZ:
            tz = TERRITORY_TZ[st]; method = "territory_rule"
            note = f"timezonefinder=None;按属地规则 state={st} -> {tz}"
        elif st == "AK":
            tz = alaska_tz(r["lon"]); method = "alaska_lon_rule"
            note = f"timezonefinder=None;按阿拉斯加经度粗分 lon={r['lon']:.2f} -> {tz}"
        else:
            # 兜底：在已有结果里找同州最近点
            known = df[df["tz_iana"].notna()] if "tz_iana" in df.columns else None
            tz = None; method = "unresolved"; note = "timezonefinder=None且无推断规则"
        tz_fail += 1
        none_rows.append((r["airport_code"], r["lat"], r["lon"], st, tz, note))
    else:
        tz_success += 1
    df.at[i, "tz_iana"] = tz
    df.at[i, "tz_method"] = method
    df.at[i, "tz_note"] = note

# ---------- 6. 金标准断言 ----------
GOLD = {
    "JFK": "America/New_York",
    "ORD": "America/Chicago",
    "LAX": "America/Los_Angeles",
    "DEN": "America/Denver",
    "PHX": "America/Phoenix",
}
gold_results = []
for code, expect in GOLD.items():
    row = df[df.airport_code == code]
    if row.empty:
        gold_results.append((code, expect, "<missing>", "FAIL: airport not in list"))
        continue
    got = row.iloc[0]["tz_iana"]
    ok = (got == expect)
    gold_results.append((code, expect, got, "PASS" if ok else f"FAIL: expected {expect}, got {got}"))

# ---------- 7. 写出 ----------
out = df[["airport_code", "bts_airport_id", "lat", "lon", "coord_source",
          "tz_iana", "tz_method", "tz_note"]].copy()
out.to_csv(OUTDIR / "airport_timezones.csv", index=False, encoding="utf-8")

# ---------- 8. 控制台摘要 ----------
print("\n=== GOLD STANDARD ===")
for g in gold_results:
    print(g)
print(f"\n=== TZ SUMMARY === airports={len(df)} success={tz_success} fail={tz_fail}")
print("coord_source:", coord_counter)
print("None rows (inferred or unresolved):")
for nr in none_rows:
    print("  ", nr)

# 把摘要吐到 stdout 末尾供脚本外捕获；日志由 03_state_check 统一写
Path(ROOT / "cleaning" / "_tz_summary.json").write_text(json.dumps({
    "n_airports": len(df),
    "tz_success": tz_success,
    "tz_fail": tz_fail,
    "coord_source": coord_counter,
    "gold": [{"code": c, "expect": e, "got": g, "result": r} for c, e, g, r in gold_results],
    "none_rows": [{"code": a, "lat": la, "lon": lo, "state": s, "tz": t, "note": n}
                  for (a, la, lo, s, t, n) in none_rows],
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n[done] wrote", OUTDIR / "airport_timezones.csv")
