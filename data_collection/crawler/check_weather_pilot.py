from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import csv
import hashlib
import json

project = Path(__file__).resolve().parent.parent
folder = project / "data/raw/NOAA/2024"
metadata = project / "metadata"
metadata.mkdir(parents=True, exist_ok=True)

plan_path = metadata / "noaa_full_airports_2024.csv"
with plan_path.open(encoding="utf-8-sig", newline="") as f:
    plan = list(csv.DictReader(f))

station_ids = sorted({r["station_id"] for r in plan})
paths = [folder / f"{s}.csv" for s in station_ids]

for path in paths:
    if not path.exists():
        raise SystemExit(f"找不到文件：{path}")

results = []

for path in paths:
    with path.open("rb") as f:
        checksum = hashlib.file_digest(f, "sha256").hexdigest()

    types = Counter()
    months = Counter()
    locations = Counter()
    names = set()
    call_signs = set()
    count = 0
    wrong_station = 0
    invalid_dates = 0
    outside_2024 = 0
    earliest = None
    latest = None

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        required = {
            "STATION", "DATE", "REPORT_TYPE",
            "LATITUDE", "LONGITUDE", "NAME"
        }

        if not required.issubset(fields):
            raise SystemExit(f"{path.name} 缺少必要字段。")

        for row in reader:
            count += 1
            types[row["REPORT_TYPE"]] += 1
            locations[
                (row["LATITUDE"], row["LONGITUDE"])
            ] += 1
            names.add(row["NAME"])
            call_signs.add(row.get("CALL_SIGN", ""))

            if row["STATION"] != path.stem:
                wrong_station += 1

            try:
                dt = datetime.fromisoformat(
                    row["DATE"].replace("Z", "+00:00")
                )
            except ValueError:
                invalid_dates += 1
                continue

            # NOAA Global Hourly的DATE按UTC时间解释。
            dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None \
                else dt.astimezone(timezone.utc)

            earliest = dt if earliest is None else min(earliest, dt)
            latest = dt if latest is None else max(latest, dt)

            if dt.year == 2024:
                months[f"{dt.month:02d}"] += 1
            else:
                outside_2024 += 1

    missing_months = [
        f"{m:02d}" for m in range(1, 13)
        if f"{m:02d}" not in months
    ]

    result = {
        "source": "NOAA Global Hourly",
        "station_id": path.stem,
        "download_url":
            f"https://noaa-global-hourly-pds.s3.amazonaws.com/2024/{path.name}",
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": checksum,
        "records": count,
        "fields": fields,
        "start_utc": earliest.isoformat() if earliest else None,
        "end_utc": latest.isoformat() if latest else None,
        "monthly_records_2024": dict(sorted(months.items())),
        "missing_months_2024": missing_months,
        "report_types": dict(types),
        "fm15_fm16_records": types["FM-15"] + types["FM-16"],
        "station_names": sorted(names),
        "call_signs": sorted(call_signs),
        "locations": [
            {"latitude": lat, "longitude": lon, "records": n}
            for (lat, lon), n in locations.items()
        ],
        "wrong_station_records": wrong_station,
        "invalid_date_records": invalid_dates,
        "outside_2024_records": outside_2024,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "downloaded_at": None
    }
    results.append(result)

    print(f"\n文件：{path.name}")
    print(f"记录数：{count:,}")
    print(f"文件大小：{result['bytes']:,} 字节")
    print(f"日期范围：{result['start_utc']} 至 {result['end_utc']}")
    print(f"2024年缺少记录的月份：{missing_months or '无'}")
    print(f"观测类型：{dict(types)}")
    print(f"FM-15/FM-16记录数：{result['fm15_fm16_records']:,}")
    print(f"站点名称：{sorted(names)}")
    print(f"位置及记录数：{dict(locations)}")
    print(f"站点编号不一致：{wrong_station}")
    print(f"日期无法解析：{invalid_dates}")
    print(f"不属于2024年的记录：{outside_2024}")

output = metadata / "noaa_full_inventory_2024.json"
output.write_text(
    json.dumps(results, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(f"\n检查记录已保存到：{output}")
print("月份齐全不代表逐日、逐小时无缺测。")

total_bytes = sum(r["bytes"] for r in results)
total_records = sum(r["records"] for r in results)
total_fm = sum(r["fm15_fm16_records"] for r in results)

problem_stations = [
    r["station_id"]
    for r in results
    if (
        r["records"] == 0
        or r["missing_months_2024"]
        or r["wrong_station_records"]
        or r["invalid_date_records"]
        or r["outside_2024_records"]
        or r["fm15_fm16_records"] == 0
    )
]

print("\n========== 正式天气采集检查汇总 ==========")
print(f"已检查站点数：{len(results)}")
print(f"CSV体积合计：{total_bytes:,} 字节")
print(f"CSV体积合计：{total_bytes / 1_000_000:.2f} MB")
print(f"全部观测记录数：{total_records:,}")
print(f"FM-15/FM-16记录数：{total_fm:,}")
print(f"存在上述基本检查异常的站点：{problem_stations or '无'}")

# 仅展示BTS与本批NOAA文件的体积比例，不是最终有效规模认定。
bts_bytes = 3_201_887_863
share = bts_bytes / (bts_bytes + total_bytes)

print(f"BTS在BTS+本批NOAA文件中的体积占比：{share:.2%}")
print("以上为文件体积统计；SGU映射疑问和天气字段质量仍需另行核验。")