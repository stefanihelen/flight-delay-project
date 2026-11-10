"""Read source manifests and local sizes; never use a hard-coded BTS byte count."""
import argparse
import csv
import json
from pathlib import Path
from _member1_common import bts_size_audit, read_json, relative, utc_now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_root.resolve()
    bts_manifest, _, bts_bytes = bts_size_audit(root)
    plan_path = root / "metadata/noaa_full_airports_2024.csv"
    with plan_path.open(encoding="utf-8-sig", newline="") as stream:
        ids = sorted({row["station_id"] for row in csv.DictReader(stream)})
    if not ids or any(not s or len(s) != 11 or not s.isalnum() for s in ids):
        raise ValueError("正式NOAA清单站点编号为空或格式异常")
    inventory = read_json(root / "metadata/noaa_full_inventory_2024.json")
    indexed = {row["station_id"]: row for row in inventory}
    if len(indexed) != len(inventory):
        raise ValueError("NOAA检查记录存在重复站点，停止重复计量")
    if set(indexed) != set(ids):
        raise ValueError("正式NOAA清单与检查记录的站点集合不一致，请先更新检查结果")
    noaa_bytes = 0
    for station in ids:
        path = root / f"data/raw/NOAA/2024/{station}.csv"
        size = path.stat().st_size
        if size != int(indexed[station]["bytes"]):
            raise ValueError(f"NOAA文件大小与检查记录不一致：{station}")
        noaa_bytes += size
    total = bts_bytes + noaa_bytes
    result = {
        "checked_at_utc": utc_now(),
        "bts_manifest": relative(bts_manifest, root),
        "bts_months": 12,
        "bts_csv_bytes": bts_bytes,
        "noaa_formal_stations": len(ids),
        "noaa_csv_bytes": noaa_bytes,
        "main_sources_csv_bytes": total,
        "bts_share_in_main_sources": bts_bytes / total,
        "noaa_share_in_main_sources": noaa_bytes / total,
        "size_checks": {
            "main_total_at_least_2_decimal_GB": total >= 2_000_000_000,
            "each_main_at_least_200_decimal_MB": min(bts_bytes, noaa_bytes) >= 200_000_000,
            "max_main_share_at_most_80_percent": max(bts_bytes, noaa_bytes) / total <= 0.8
        },
        "basis": "12个月BTS解压CSV与正式NOAA清单CSV；不计ZIP副本、样本或SGU试采集。",
        "limitation": "这是原始文件体积核算，不替代有效字段/报告类型口径、质量核验或完整文件SHA核验。"
    }
    out = root / "metadata/source_size_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"BTS：{bts_bytes:,} 字节；NOAA：{noaa_bytes:,} 字节")
    print(f"合计：{total:,} 字节；BTS占比：{bts_bytes / total:.2%}")
    print("文件规模条件：", result["size_checks"])
    print("动态核算记录已保存：metadata/source_size_audit.json")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"核算失败，未出具通过结论：{exc}")
