"""Export reproducible, non-random raw subsets from the user's existing files; no network."""
import argparse
import csv
import json
import shutil
import uuid
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from _member1_common import bts_size_audit, read_json, relative, sha256, utc_now

AIRPORTS = ("JFK", "ORD", "LAX")
DATES = ("2024-01-09", "2024-07-09")
MATCH_WINDOW_MINUTES = 90
# Conservative UTC envelope, not a per-flight time conversion: for each selected
# local departure date D, retain [D-1 00:00 UTC, D+2 00:00 UTC). These mainland
# US airports have UTC offsets in [-8,-4] on the selected dates; this envelope
# includes next-day 2400, all local departure times, and 90-minute prior observations.
# No claim of per-flight matching or timezone assignment is made here.
WINDOWS = [
    (datetime.combine(date.fromisoformat(d) - timedelta(days=1), time(), timezone.utc),
     datetime.combine(date.fromisoformat(d) + timedelta(days=2), time(), timezone.utc))
    for d in DATES
]


def utc_time(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def flag(value):
    try:
        n = Decimal(value.strip())
        return int(n) if n in (Decimal(0), Decimal(1)) else None
    except (InvalidOperation, ValueError, AttributeError):
        return None


def verify_known(path, known):
    if "bytes" in known and path.stat().st_size != int(known["bytes"]):
        raise ValueError(f"原始文件体积与既有记录不一致：{path.name}")
    actual = sha256(path)
    if known.get("sha256") and actual != known["sha256"]:
        raise ValueError(f"原始文件SHA-256与既有记录不一致：{path.name}")
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_root.resolve()
    target = root / "data/samples/raw/member1"
    if target.exists():
        raise ValueError("样本目录已存在，已保留，不覆盖。需重导时请先将整个member1样本目录移到备份位置。")
    manifest_path, manifest, _ = bts_size_audit(root)
    with (root / "metadata/noaa_full_airports_2024.csv").open(encoding="utf-8-sig", newline="") as stream:
        plan = list(csv.DictReader(stream))
    mapping = {}
    for airport in AIRPORTS:
        candidates = [row for row in plan if row["airport_code"] == airport]
        if len(candidates) != 1 or not candidates[0]["station_id"]:
            raise ValueError(f"正式清单中{airport}映射不唯一或缺少站点")
        mapping[airport] = candidates[0]
    if len({row["station_id"] for row in mapping.values()}) != len(AIRPORTS):
        raise ValueError("本样本方案要求3机场分别对应3个站点，请核对映射")
    noaa_inventory = {row["station_id"]: row for row in read_json(root / "metadata/noaa_full_inventory_2024.json")}
    aux_sources = [
        (root / "data/raw/OurAirports/airports.csv", "OurAirports/airports.csv", "metadata/ourairports_inventory.json"),
        (root / "data/raw/Census/cb_2024_us_state_500k.zip", "Census/cb_2024_us_state_500k.zip", "metadata/census_state_inventory.json")
    ]
    for path, _, _ in aux_sources:
        if not path.is_file():
            raise FileNotFoundError(path)
    selected_months = {d[:7] for d in DATES}
    sources = []
    groups = Counter()
    categories = Counter()
    notes = []
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.parent / (".member1_staging_" + uuid.uuid4().hex)
    stage.mkdir()
    print("开始从现有数据导出样本，不会联网，不会修改data/raw。", flush=True)
    try:
        flights_path = stage / "BTS/bts_flights_sample.csv"
        flights_path.parent.mkdir(parents=True)
        lineage_path = stage / "BTS/flight_sample_lineage.csv"
        selected_count = 0
        header = None
        with flights_path.open("w", encoding="utf-8-sig", newline="") as dst, lineage_path.open("w", encoding="utf-8-sig", newline="") as trace:
            writer = csv.writer(dst)
            lineage = csv.writer(trace)
            lineage.writerow(["sample_data_row_number", "source_csv", "source_csv_record_number_including_header"])
            for entry in sorted(manifest["files"], key=lambda row: row["month"]):
                if entry["month"] not in selected_months:
                    continue
                path = manifest_path.parent / entry["csv_member"]
                original_hash = verify_known(path, {"bytes": entry["csv_bytes"], "sha256": entry.get("csv_sha256")})
                scanned = 0
                with path.open(encoding="utf-8-sig", newline="") as src:
                    reader = csv.reader(src)
                    current = next(reader)
                    if header is None:
                        header = current
                        for key in ("Origin", "FlightDate", "CRSDepTime", "Cancelled", "Diverted", "ArrDel15"):
                            if current.count(key) != 1:
                                raise ValueError(f"BTS必要字段缺失或不唯一：{key}")
                        indices = {key: current.index(key) for key in ("Origin", "FlightDate", "Cancelled", "Diverted", "ArrDel15")}
                        writer.writerow(header)
                    elif current != header:
                        raise ValueError("两个原始月度CSV表头不同，不自动拼接或改字段")
                    for record_number, row in enumerate(reader, 2):
                        scanned += 1
                        if scanned % 100000 == 0:
                            print(f"正在读取{entry['month']}：{scanned:,}条……", flush=True)
                        if len(row) != len(header):
                            raise ValueError(f"BTS原始CSV记录字段数异常：{path.name} 记录{record_number}")
                        airport = row[indices["Origin"]]
                        day = row[indices["FlightDate"]][:10]
                        if airport not in AIRPORTS or day not in DATES:
                            continue
                        writer.writerow(row)
                        selected_count += 1
                        lineage.writerow([selected_count, relative(path, root), record_number])
                        groups[(airport, day)] += 1
                        cancelled = flag(row[indices["Cancelled"]])
                        diverted = flag(row[indices["Diverted"]])
                        delayed = flag(row[indices["ArrDel15"]])
                        if cancelled == 1:
                            categories["cancelled"] += 1
                        elif diverted == 1:
                            categories["diverted"] += 1
                        elif cancelled == 0 and diverted == 0 and delayed == 1:
                            categories["noncancelled_nondiverted_arrdel15_1"] += 1
                        elif cancelled == 0 and diverted == 0 and delayed == 0:
                            categories["noncancelled_nondiverted_arrdel15_0"] += 1
                        else:
                            categories["other_or_missing_label"] += 1
                if scanned != int(entry["records"]):
                    raise ValueError(f"月度读取条数与来源清单不同：{path.name}")
                sources.append({"source": "BTS", "path": relative(path, root), "bytes": path.stat().st_size,
                                "sha256": original_hash, "records_scanned": scanned,
                                "official_url": entry.get("url"), "upstream_acquired_utc": entry.get("acquired_utc")})
                print(f"已扫描{entry['month']}：{scanned:,}条，累计选出{selected_count:,}条。", flush=True)
        for airport in AIRPORTS:
            for day in DATES:
                if not groups[(airport, day)]:
                    raise ValueError(f"所选{airport}/{day}没有原始航班，不自动变更方案或补造记录")
        if not categories["cancelled"] or not categories["noncancelled_nondiverted_arrdel15_1"] or not categories["noncancelled_nondiverted_arrdel15_0"]:
            notes.append("本样本未自然覆盖全部正常/延误/取消类别；保留真实结果，不调整原始标签凑类别。")
        weather_summaries = []
        for airport, airport_row in mapping.items():
            station = airport_row["station_id"]
            path = root / f"data/raw/NOAA/2024/{station}.csv"
            known = noaa_inventory[station]
            original_hash = verify_known(path, known)
            destination = stage / f"NOAA/{station}.csv"
            destination.parent.mkdir(exist_ok=True)
            weather_count = 0
            report_types = Counter()
            bounds = [None, None]
            utc_window_counts = [0] * len(WINDOWS)
            metar_counts = [0] * len(WINDOWS)
            scanned = 0
            with path.open(encoding="utf-8-sig", newline="") as src, destination.open("w", encoding="utf-8-sig", newline="") as dst:
                reader = csv.reader(src)
                fields = next(reader)
                for key in ("STATION", "DATE", "REPORT_TYPE"):
                    if fields.count(key) != 1:
                        raise ValueError(f"NOAA必要字段缺失或不唯一：{station}/{key}")
                pos = {key: fields.index(key) for key in ("STATION", "DATE", "REPORT_TYPE")}
                writer = csv.writer(dst)
                writer.writerow(fields)
                for row in reader:
                    scanned += 1
                    if len(row) != len(fields) or row[pos["STATION"]] != station:
                        raise ValueError(f"NOAA字段数或站点编号异常：{station}")
                    dt = utc_time(row[pos["DATE"]])
                    windows = [i for i, (lo, hi) in enumerate(WINDOWS) if lo <= dt < hi]
                    if not windows:
                        continue
                    writer.writerow(row)
                    weather_count += 1
                    report_type = row[pos["REPORT_TYPE"]]
                    report_types[report_type] += 1
                    bounds[0] = dt if bounds[0] is None else min(bounds[0], dt)
                    bounds[1] = dt if bounds[1] is None else max(bounds[1], dt)
                    for i in windows:
                        utc_window_counts[i] += 1
                        if report_type.strip() in ("FM-15", "FM-16"):
                            metar_counts[i] += 1
            if scanned != int(known["records"]):
                raise ValueError(f"NOAA实际条数与原始检查清单不同：{station}")
            if not all(metar_counts):
                raise ValueError(f"{airport}至少一个所选日期的UTC包络内没有FM-15/FM-16观测；不出具可关联样本结论")
            weather_summaries.append({"airport": airport, "station_id": station, "records": weather_count,
                                      "report_types": dict(report_types), "start_utc": bounds[0].isoformat(),
                                      "end_utc": bounds[1].isoformat(), "records_per_utc_window": utc_window_counts,
                                      "fm15_fm16_per_utc_window": metar_counts})
            sources.append({"source": "NOAA", "path": relative(path, root), "bytes": path.stat().st_size,
                            "sha256": original_hash, "records_scanned": scanned, "download_url": known.get("download_url")})
            print(f"天气{airport}/{station}：保留{weather_count:,}条原始观测。", flush=True)
        for path, dest, inventory_name in aux_sources:
            known = read_json(root / inventory_name)
            check = dict(known)
            if "zip_bytes" in known:
                check["bytes"] = known["zip_bytes"]
            original_hash = verify_known(path, check)
            destination = stage / dest
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(path, destination)
            if sha256(destination) != original_hash:
                raise ValueError(f"辅助原始文件复制校验失败：{path.name}")
            sources.append({"source": dest.split("/")[0], "path": relative(path, root), "bytes": path.stat().st_size,
                            "sha256": original_hash, "copied_full_file": True,
                            "records": known.get("records", known.get("active_records"))})
        mapping_path = stage / "airport_station_sample_mapping.csv"
        with mapping_path.open("w", encoding="utf-8-sig", newline="") as f:
            fields = list(next(iter(mapping.values())))
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(mapping.values())
        outputs = []
        for path in sorted(stage.rglob("*")):
            if not path.is_file():
                continue
            name = path.relative_to(stage).as_posix()
            item = {"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            if path.suffix.lower() == ".csv":
                with path.open(encoding="utf-8-sig", newline="") as f:
                    reader = csv.reader(f)
                    next(reader)
                    item["records"] = sum(1 for _ in reader)
            outputs.append(item)
        sample_manifest = {
            "generated_at_utc": utc_now(), "completed": True,
            "selection": {"origin_airports": list(AIRPORTS), "local_flight_dates": list(DATES),
                          "rule": "保留所选出发机场及当地航班日期的全部原始航班，不按结果筛选或改标签。",
                          "random_sampling": False, "random_seed": None,
                          "csv_serialization": "保留原字段顺序、字段值和记录顺序；CSV重新序列化，不宣称与源文件片段字节相同。"},
            "weather_selection": {"utc_windows_inclusive_start_exclusive_end": [[lo.isoformat(), hi.isoformat()] for lo, hi in WINDOWS],
                                  "basis": "当地日期的保守UTC包络：D-1 00:00至D+2 00:00；覆盖所选美国本土机场的跨日及90分钟前序观测需求。",
                                  "exact_per_flight_timezone_conversion_performed": False,
                                  "per_flight_90_minute_match_performed": False,
                                  "all_original_report_types_kept": True},
            "flight_records": selected_count,
            "flight_records_by_origin_and_local_date": [{"origin": a, "flight_date": d, "records": groups[(a, d)]} for a in AIRPORTS for d in DATES],
            "raw_label_counts": dict(categories), "weather": weather_summaries,
            "source_bts_manifest": relative(manifest_path, root),
            "input_control_files": [
                {"path": relative(p, root), "bytes": p.stat().st_size, "sha256": sha256(p)}
                for p in [manifest_path, root / "metadata/noaa_full_airports_2024.csv",
                          root / "metadata/noaa_full_inventory_2024.json",
                          root / "metadata/ourairports_inventory.json",
                          root / "metadata/census_state_inventory.json"]
            ],
            "original_sources": sources,
            "outputs": outputs, "warnings": notes,
            "use": "仅用于展示与读取/关联测试，不代表全年统计，不替代全量分析，不计入新增有效体积。"
        }
        (stage / "sample_manifest.json").write_text(json.dumps(sample_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        # Checksum every deliverable after the actual counts have been determined.
        (stage / "checksums.sha256").write_text("\n".join(item["sha256"] + "  " + item["path"] for item in outputs) + "\n", encoding="utf-8")
        group_table = "\n".join(f"| {a} | {d} | {groups[(a,d)]:,} |" for a in AIRPORTS for d in DATES)
        weather_table = "\n".join(f"| {r['airport']} | {r['station_id']} | {r['records']:,} | {r['start_utc']} | {r['end_utc']} |" for r in weather_summaries)
        readme = f'''# 成员1代表性原始样本\n\n本样本由export_raw_samples.py从本项目已有原始文件导出。只用于展示与读取／后续关联测试，不用于代表全年分布或替代全量分析。没有联网重采集，没有清洗、填补、去重、过滤天气质量码或生成融合表。\n\n## 选取规则\n\n固定选择JFK、ORD、LAX三个出发机场，以及当地航班日期2024-01-09和2024-07-09，保留范围内全部航班原始记录。规则为确定性范围选择，不使用随机抽样或随机种子，不按正常、延误或取消结果挑选记录。原始表头、字段顺序和值保留，包括空列名；CSV重新序列化，源字节哈希与导出文件哈希分别记录。\n\n| 出发机场 | 当地航班日期 | 实际航班条数 |\n|---|---|---:|\n{group_table}\n\n航班实际合计：{selected_count:,}条。原始标签计数为{dict(categories)}；这些仅用于检查样本自然包含的情况，不是项目统计结论。未自然覆盖的类别不补造。\n\n## 对应天气\n\n按正式映射清单选取对应3站；每个所选当地日期D的天气保留UTC区间[D-1日00:00, D+2日00:00)，即2024-01-08至2024-01-11、2024-07-08至2024-07-11，均起点包含、终点不包含。所选机场为美国本土JFK、ORD、LAX；该保守包络覆盖当地计划时间转换UTC后的跨日范围、2400和至少90分钟前序观测需要。并未逐班转换时区或执行90分钟天气匹配；窗口内存在FM-15/FM-16不保证每班都能匹配，成员2仍需精确对齐、处理缺测及质量码。保留窗口内全部原报告类型，不把日／月汇总当成METAR。\n\n| 机场 | 站点 | 实际天气条数 | 首条UTC | 末条UTC |\n|---|---|---:|---|---|\n{weather_table}\n\n天气总条数：{sum(r['records'] for r in weather_summaries):,}。每个窗口的实际条数及FM-15/FM-16条数见sample_manifest.json。\n\n## 其他原始资料与证据\n\nOurAirports完整airports.csv与Census完整ZIP按字节复制，不把辅助文件副本计入额外规模。州界ZIP保留全部配套文件；使用时一起解压SHP、SHX、DBF、PRJ等。Census原坐标系为NAD83，不能未经核对当成WGS84。\n\n原始来源版本由sample_manifest.json中的原文件路径、SHA-256和字节数识别；BTS上游时间来自原始manifest，不替代本次样本生成时间。BTS/flight_sample_lineage.csv记录样本数据行序号到原月度CSV逻辑记录序号的关系，不把逻辑记录号误称为物理文本行号。checksums.sha256核对导出数据及映射文件；sample_manifest.json在文件导出后据实际读取条数生成。\n\nSGU位置冲突、XWA未匹配、WYS部分年份覆盖仍保留在全量来源说明，不因样本未选它们而消失。来源类别口径和最终融合质量仍需全组核验。\n\n生成时间UTC：{sample_manifest['generated_at_utc']}。\n'''
        if notes:
            readme += "\n注意：" + "；".join(notes) + "\n"
        (stage / "README.md").write_text(readme, encoding="utf-8")
        # Re-read every exported CSV and verify checksums before announcing completion.
        for item in outputs:
            path = stage / item["path"]
            if sha256(path) != item["sha256"]:
                raise ValueError("导出文件最终校验不一致：" + item["path"])
        stage.rename(target)
        receipt = {"completed": True, "generated_at_utc": sample_manifest["generated_at_utc"],
                   "sample_directory": relative(target, root), "flight_records": selected_count,
                   "weather_records": sum(row["records"] for row in weather_summaries),
                   "sample_manifest_sha256": sha256(target / "sample_manifest.json")}
        (root / "metadata/member1_sample_export_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n========== 成员1样本导出完成 ==========")
        print(f"航班样本：{selected_count:,}条")
        print(f"天气样本：{receipt['weather_records']:,}条；3个站点")
        print("原始标签计数：", dict(categories))
        print("原始数据目录未改写；所有样本CSV已重新读取并校验。")
        print("样本及自动抽样说明：data/samples/raw/member1/")
        print("导出回执：metadata/member1_sample_export_receipt.json")
        for note in notes:
            print("注意：", note)
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"样本未完成：{exc}")
