from pathlib import Path
import csv

project = Path(__file__).resolve().parent.parent
metadata = project / "metadata"

source = metadata / "airport_station_mapping_reviewed.csv"

with source.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    columns = reader.fieldnames
    rows = list(reader)

# 正式采集使用已通过规则或历史代码交叉核对的机场。
allowed = {
    "ready_for_trial_download",
    "historical_alias_crosschecked"
}

selected = [
    r for r in rows
    if r["collection_status"] in allowed and r["station_id"]
]

# 优先排列出发航班量较大的机场。
selected.sort(key=lambda r: int(r["departures"]), reverse=True)

output = metadata / "noaa_full_airports_2024.csv"

with output.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    writer.writerows(selected)

station_ids = {r["station_id"] for r in selected}

# 下载清单中已有的站点，不需要重复下载。
manifest_path = metadata / "noaa_download_manifest_2024.json"

import json

existing = {}
if manifest_path.exists():
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))

recorded = {
    s for s in station_ids
    if existing.get(s, {}).get("sha256")
    and (project / "data/raw/NOAA/2024" / f"{s}.csv").exists()
}

excluded = [
    r for r in rows
    if r["collection_status"] not in allowed
]

print(f"正式采集机场数：{len(selected)}")
print(f"去重后的天气站数：{len(station_ids)}")
print(f"已有文件且具备校验记录的站点：{len(recorded)}")
print(f"其余计划下载站点：{len(station_ids - recorded)}")
print("已有文件仍需重新核对大小与SHA-256，才能跳过下载。")

print("\n暂未纳入正式采集的机场：")
for r in excluded:
    print(f'{r["airport_code"]}：{r["collection_status"]}')

print(f"\n正式采集清单已保存到：{output}")
print("SGU已下载的试采集文件保留，不删除。")