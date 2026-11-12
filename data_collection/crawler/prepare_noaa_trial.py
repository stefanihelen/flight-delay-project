from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import csv
import json

project = Path(__file__).resolve().parent.parent
metadata = project / "metadata"

with (metadata / "airport_station_mapping.csv").open(
    encoding="utf-8-sig", newline=""
) as f:
    rows = list(csv.DictReader(f))

pilot = json.loads(
    (metadata / "noaa_pilot_inventory.json").read_text(
        encoding="utf-8"
    )
)
pilot = {r["station_id"]: r for r in pilot}

expected = {
    "PBI": "72203012844",
    "SGU": "72475423186"
}

# 核对已检查的两个样本，避免直接修改错误的映射。
for code, station in expected.items():
    matched = [r for r in rows if r["airport_code"] == code]
    if len(matched) != 1 or matched[0]["station_id"] != station:
        raise SystemExit(f"{code}映射与预期不一致，请先检查。")

    info = pilot.get(station)
    if not info or info["records"] == 0:
        raise SystemExit(f"缺少{station}的有效样本检查记录。")

    if (
        info["wrong_station_records"]
        or info["invalid_date_records"]
        or info["outside_2024_records"]
        or info["missing_months_2024"]
    ):
        raise SystemExit(f"{station}的样本检查存在异常，请先检查。")

now = datetime.now(timezone.utc).isoformat()

for r in rows:
    r["collection_status"] = (
        "ready_for_trial_download"
        if r["status"] == "auto_code_distance_match"
        else "pending_review"
    )
    r["review_note"] = ""
    r["evidence_url"] = ""
    r["review_recorded_at_utc"] = ""

    if r["airport_code"] == "PBI":
        r["collection_status"] = "historical_alias_crosschecked"
        r["review_note"] = (
            "原映射保留历史机场标识；NOAA目录和2024样本"
            "支持West Palm Beach机场身份，距离约0.393公里；"
            "不代表逐小时观测完整。"
        )
        r["evidence_url"] = (
            "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
            ";https://noaa-global-hourly-pds.s3.amazonaws.com/"
            "2024/72203012844.csv"
        )
        r["review_recorded_at_utc"] = now

    elif r["airport_code"] == "SGU":
        r["collection_status"] = "trial_only_location_conflict"
        r["review_note"] = (
            "2024样本覆盖12个月，但仍使用37.1,-113.6坐标；"
            "NWS历史通知记录KSGU位置调整。保留原坐标和距离，"
            "允许试采集，正式天气关联前需进一步复核。"
        )
        r["evidence_url"] = (
            "https://www.weather.gov/media/notification/tins/"
            "tin14-29nam_aaa.pdf"
        )
        r["review_recorded_at_utc"] = now

    elif r["airport_code"] == "XWA":
        r["collection_status"] = "unmatched_retained"
        r["review_note"] = (
            "当前ISD目录与25公里规则下未找到候选；"
            "保留航班和未匹配状态，不以旧ISN机场替代。"
        )
        r["evidence_url"] = (
            "https://www.govinfo.gov/content/pkg/"
            "FR-2019-08-29/pdf/2019-18577.pdf"
        )
        r["review_recorded_at_utc"] = now

def save_csv(path, data):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)

reviewed_path = metadata / "airport_station_mapping_reviewed.csv"
save_csv(reviewed_path, rows)

# 保留两个试采集样本，再按出发航班量补足30个机场。
selected = [
    next(r for r in rows if r["airport_code"] == code)
    for code in ("PBI", "SGU")
]

eligible = [
    r for r in rows
    if r["status"] == "auto_code_distance_match"
    and r["airport_code"] not in {"PBI", "SGU"}
]

for r in sorted(
    eligible, key=lambda x: int(x["departures"]), reverse=True
):
    if len(selected) >= 30:
        break
    selected.append(r)

if len(selected) != 30:
    raise SystemExit("可用机场不足30个，请检查映射表。")

plan_path = metadata / "noaa_trial_airports_30.csv"
save_csv(plan_path, selected)

station_count = len({r["station_id"] for r in selected})

print("修订映射表已保存：", reviewed_path)
print("原始status与reason字段保持不变，新增采集状态及复核说明。")
print("\n采集状态统计：")
for status, count in sorted(
    Counter(r["collection_status"] for r in rows).items()
):
    print(f"{status}：{count}")

print(f"\n试采集机场数：{len(selected)}")
print(f"去重后的天气站数：{station_count}")
print("试采集清单已保存：", plan_path)
print("SGU仍为位置冲突候选，列入试采集不等于映射已确认。")