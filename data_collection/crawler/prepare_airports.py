from pathlib import Path
from tkinter import Tk, filedialog
from datetime import datetime, timezone
import csv
import hashlib
import json

project = Path(__file__).resolve().parent.parent
metadata = project / "metadata"
metadata.mkdir(parents=True, exist_ok=True)

# 一、检查NOAA站点目录
station_path = project / "data" / "raw" / "NOAA" / "isd-history.csv"

if not station_path.exists():
    raise SystemExit(f"找不到站点目录：{station_path}")

with station_path.open("rb") as f:
    station_hash = hashlib.file_digest(f, "sha256").hexdigest()

with station_path.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames or []
    required = {"USAF", "WBAN", "STATION NAME", "ICAO",
                "LAT", "LON", "BEGIN", "END"}

    if not required.issubset(fields):
        raise SystemExit("站点目录缺少必要字段，请检查下载文件。")

    stations = list(reader)

available = sum(
    1 for s in stations
    if s["BEGIN"] and s["END"]
    and s["BEGIN"] <= "20241231"
    and s["END"] >= "20240101"
)

station_info = {
    "source": "NOAA",
    "filename": station_path.name,
    "download_url":
        "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv",
    "bytes": station_path.stat().st_size,
    "sha256": station_hash,
    "records": len(stations),
    "records_overlapping_2024": available,
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "downloaded_at": None
}

(metadata / "noaa_station_directory_inventory.json").write_text(
    json.dumps(station_info, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(f"NOAA目录检查通过，共 {len(stations):,} 条站点记录。")
print(f"观测起止日期与2024年有交集的记录：{available:,}")
print("注意：日期有交集，不保证2024年每天都有观测。\n")

# 二、选择此前解压的全年航班文件夹
root = Tk()
root.withdraw()
selected = filedialog.askdirectory(
    title="请选择包含12个月CSV和file_manifest.json的文件夹"
)
root.destroy()

if not selected:
    raise SystemExit("未选择航班文件夹，已停止。")

folder = Path(selected)
manifest_path = folder / "file_manifest.json"

if not manifest_path.exists():
    raise SystemExit("没有找到file_manifest.json，请重新选择文件夹。")

files = json.loads(
    manifest_path.read_text(encoding="utf-8")
)["files"]

expected = {f"2024-{m:02d}" for m in range(1, 13)}
if len(files) != 12 or {x["month"] for x in files} != expected:
    raise SystemExit("文件清单未完整覆盖2024年12个月。")

for item in files:
    if not (folder / item["csv_member"]).exists():
        raise SystemExit(f"缺少文件：{item['csv_member']}")

# 三、逐月读取，只汇总机场身份与航班数量
airports = {}
total = 0

for item in sorted(files, key=lambda x: x["month"]):
    month_count = 0

    with (folder / item["csv_member"]).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        reader = csv.DictReader(f)

        for row in reader:
            month_count += 1

            for side, counter in (
                ("Origin", "departures"),
                ("Dest", "arrivals")
            ):
                code = row[side]
                airport_id = row[side + "AirportID"]
                key = (code, airport_id)

                if key not in airports:
                    airports[key] = {
                        "airport_code": code,
                        "bts_airport_id": airport_id,
                        "city": row[side + "CityName"],
                        "state": row[side + "State"],
                        "departures": 0,
                        "arrivals": 0
                    }

                airports[key][counter] += 1

    total += month_count
    print(f"{item['month']}：已读取 {month_count:,} 条航班")

    if month_count != item["records"]:
        raise SystemExit("实际记录数与文件清单不一致，请先检查。")

output = metadata / "bts_airports_2024.csv"
columns = [
    "airport_code", "bts_airport_id", "city", "state",
    "departures", "arrivals"
]

with output.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    writer.writerows(
        sorted(airports.values(),
               key=lambda x: (x["airport_code"], x["bts_airport_id"]))
    )

print(f"\n全年实际读取：{total:,} 条航班")
print(f"机场代码与机场ID组合数：{len(airports):,}")
print(f"机场清单已保存到：{output}")