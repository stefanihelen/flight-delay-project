from pathlib import Path
import csv
import math
from collections import Counter

project = Path(__file__).resolve().parent.parent
metadata = project / "metadata"

def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

def distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(
        math.radians, [lat1, lon1, lat2, lon2]
    )
    value = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(value)))

airports = read_csv(metadata / "bts_airports_2024.csv")
ourairports = read_csv(
    project / "data/raw/OurAirports/airports.csv"
)
history = read_csv(
    project / "data/raw/NOAA/isd-history.csv"
)

# 美国及本项目可能涉及的领地、相关太平洋地区。
countries = {"US", "PR", "VI", "GU", "AS", "MP", "UM", "FM", "PW", "MH"}
ourairports = [
    a for a in ourairports if a["iso_country"] in countries
]

# 仅保留观测起止日期与2024年有交集、坐标有效的站点。
stations = []
for s in history:
    if not (
        s["BEGIN"] and s["END"]
        and s["BEGIN"] <= "20241231"
        and s["END"] >= "20240101"
    ):
        continue

    try:
        lat, lon = float(s["LAT"]), float(s["LON"])
    except (ValueError, TypeError):
        continue

    if -90 <= lat <= 90 and -180 <= lon <= 180:
        stations.append((s, lat, lon))

results = []
candidate_rows = []

for airport in airports:
    code = airport["airport_code"]
    matches = [
        a for a in ourairports if a["iata_code"] == code
    ]
    airport_method = "iata_code"

    # 当前机场快照可能更换代码。
    # 只为候选复核寻找保留旧标识和关键词的记录，不自动确认。
    if not matches:
        matches = [
            a for a in ourairports
            if a["ident"] == "K" + code
            and code in {
                word.strip()
                for word in a.get("keywords", "").split(",")
            }
        ]
        airport_method = "historical_identifier_candidate"

    result = {
        **airport,
        "ourairports_ident": "",
        "airport_name": "",
        "airport_latitude": "",
        "airport_longitude": "",
        "airport_match_method": airport_method,
        "station_id": "",
        "station_name": "",
        "station_icao": "",
        "station_latitude": "",
        "station_longitude": "",
        "distance_km": "",
        "station_begin": "",
        "station_end": "",
        "status": "",
        "reason": ""
    }

    if len(matches) != 1:
        result["status"] = "review_airport"
        result["reason"] = f"机场资料候选数量为{len(matches)}，需核对机场身份"
        results.append(result)
        continue

    a = matches[0]
    try:
        alat = float(a["latitude_deg"])
        alon = float(a["longitude_deg"])
        if not (-90 <= alat <= 90 and -180 <= alon <= 180):
            raise ValueError
    except (ValueError, TypeError):
        result["status"] = "review_airport"
        result["reason"] = "机场坐标无效"
        results.append(result)
        continue

    result.update({
        "ourairports_ident": a["ident"],
        "airport_name": a["name"],
        "airport_latitude": alat,
        "airport_longitude": alon
    })

    airport_codes = {
        a.get("icao_code", ""), a["ident"], a.get("gps_code", "")
    } - {""}

    candidates = []
    for s, slat, slon in stations:
        km = distance_km(alat, alon, slat, slon)
        if km > 25:
            continue

        same_code = s["ICAO"] in airport_codes
        full_period = (
            s["BEGIN"] <= "20240101"
            and s["END"] >= "20241231"
        )
        candidates.append((s, km, same_code, full_period, slat, slon))

    # 优先代码一致，再优先记录起止日期覆盖全年，最后比较距离。
    candidates.sort(
        key=lambda x: (
            not x[2], not x[3], x[1], x[0]["USAF"], x[0]["WBAN"]
        )
    )

    # 保存25公里内全部候选，便于复核选择依据。
    for rank, (s, km, same, full, slat, slon) in enumerate(candidates, 1):
        candidate_rows.append({
            "airport_code": code,
            "bts_airport_id": airport["bts_airport_id"],
            "rank": rank,
            "station_id": s["USAF"] + s["WBAN"],
            "station_name": s["STATION NAME"],
            "station_icao": s["ICAO"],
            "distance_km": round(km, 3),
            "code_match": same,
            "directory_period_covers_2024": full,
            "station_begin": s["BEGIN"],
            "station_end": s["END"]
        })

    if not candidates:
        result["status"] = "review_no_station"
        result["reason"] = "25公里内没有满足年份条件的站点"
        results.append(result)
        continue

    s, km, same, full, slat, slon = candidates[0]
    exact_candidates = [c for c in candidates if c[2]]

    result.update({
        "station_id": s["USAF"] + s["WBAN"],
        "station_name": s["STATION NAME"],
        "station_icao": s["ICAO"],
        "station_latitude": slat,
        "station_longitude": slon,
        "distance_km": round(km, 3),
        "station_begin": s["BEGIN"],
        "station_end": s["END"]
    })

    reasons = []
    if airport_method != "iata_code":
        reasons.append("使用历史机场标识候选")
    if not same:
        reasons.append("站点代码不一致，仅为空间候选")
    if km > 10:
        reasons.append("距离超过10公里")
    if len(exact_candidates) > 1:
        reasons.append("存在多个代码一致的站点")
    if not full:
        reasons.append("站点目录起止日期未覆盖全年")

    if reasons:
        result["status"] = "review_station"
        result["reason"] = "；".join(reasons)
    else:
        result["status"] = "auto_code_distance_match"
        result["reason"] = "机场代码匹配、站点代码一致、距离不超过10公里、目录日期覆盖全年"

    results.append(result)

mapping_path = metadata / "airport_station_mapping.csv"
write_csv(mapping_path, results, list(results[0]))

candidate_columns = [
    "airport_code", "bts_airport_id", "rank", "station_id",
    "station_name", "station_icao", "distance_km", "code_match",
    "directory_period_covers_2024", "station_begin", "station_end"
]
write_csv(
    metadata / "airport_station_candidates.csv",
    candidate_rows,
    candidate_columns
)

review = [
    r for r in results if r["status"] != "auto_code_distance_match"
]
write_csv(
    metadata / "airport_station_review.csv",
    review,
    list(results[0])
)

print("映射表生成完成。")
print(f"机场记录数：{len(results)}")
for status, count in sorted(Counter(r["status"] for r in results).items()):
    print(f"{status}：{count}")

print(f"\n需复核：{len(review)}条")
for r in review:
    print(
        f'{r["airport_code"]} | {r["station_id"] or "无站点"}'
        f' | {r["distance_km"]}公里 | {r["reason"]}'
    )

print(f"\n映射表保存位置：{mapping_path}")
print("自动匹配仅通过规则检查，不代表已人工确认或天气观测完整。")