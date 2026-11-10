from pathlib import Path
from datetime import datetime, timezone
import urllib.request
import urllib.error
import csv
import hashlib
import json
import time

project = Path(__file__).resolve().parent.parent
metadata = project / "metadata"
logs = project / "logs"
output = project / "data/raw/NOAA/2024"

for folder in (metadata, logs, output):
    folder.mkdir(parents=True, exist_ok=True)

plan_path = metadata / "noaa_trial_airports_30.csv"
manifest_path = metadata / "noaa_download_manifest_2024.json"
log_path = logs / "noaa_download_log.jsonl"

def now():
    return datetime.now(timezone.utc).isoformat()

def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def log(event):
    event["logged_at_utc"] = now()
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def save_manifest(data):
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temporary.replace(manifest_path)

with plan_path.open(encoding="utf-8-sig", newline="") as f:
    plan = list(csv.DictReader(f))

station_ids = sorted({r["station_id"] for r in plan})

if not station_ids or any(
    len(s) != 11 or not s.isalnum() for s in station_ids
):
    raise SystemExit("清单中存在空站点编号或格式异常，请检查。")

manifest = {}
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

# 已检查的两个手动下载文件，具有可核对的大小和校验值。
pilot_path = metadata / "noaa_pilot_inventory.json"
pilot = {}
if pilot_path.exists():
    pilot = {
        r["station_id"]: r
        for r in json.loads(pilot_path.read_text(encoding="utf-8"))
    }

successful = 0
reused = 0
failed = []

for index, station in enumerate(station_ids, 1):
    path = output / f"{station}.csv"
    url = (
        "https://noaa-global-hourly-pds.s3.amazonaws.com/"
        f"2024/{station}.csv"
    )
    print(f"\n[{index}/{len(station_ids)}] 站点 {station}", flush=True)

    # 只有与已知校验记录一致，才跳过下载。
    if path.exists():
        known = manifest.get(station)
        if not known or not known.get("sha256"):
            known = pilot.get(station)

        if (
            known
            and path.stat().st_size == known.get("bytes")
            and sha256(path) == known.get("sha256")
        ):
            record = dict(known)
            record.update({
                "station_id": station,
                "filename": path.name,
                "download_url": url,
                "last_verified_at_utc": now()
            })
            # 手动下载时间未知时保持为空，不用检查时间代替。
            record.setdefault("downloaded_at", None)
            manifest[station] = record
            save_manifest(manifest)
            log({"station_id": station, "status": "verified_existing"})
            reused += 1
            print("已存在，大小与SHA-256核对通过，跳过下载。", flush=True)
            continue

        failed.append(station)
        log({
            "station_id": station,
            "status": "existing_file_not_verified",
            "message": "现有文件缺少匹配的校验记录，保留文件，不覆盖。"
        })
        print("现有文件无法通过校验，已保留，请稍后核查。", flush=True)
        continue

    part = output / f"{station}.csv.part"
    completed = False

    for attempt in range(1, 4):
        started = now()
        log({
            "station_id": station,
            "status": "download_started",
            "attempt": attempt,
            "url": url
        })

        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "UniversityCourseResearch/1.0"}
            )

            with urllib.request.urlopen(request, timeout=60) as response:
                content_length = response.headers.get("Content-Length")
                last_modified = response.headers.get("Last-Modified")
                etag = response.headers.get("ETag")

                with part.open("wb") as f:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        f.write(block)

            received = now()

            if content_length and part.stat().st_size != int(content_length):
                raise ValueError("下载字节数与Content-Length不一致")

            # 基本内容核验：防止把错误页面保存成CSV。
            with part.open(encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames or []

                if not {"STATION", "DATE", "REPORT_TYPE"}.issubset(fields):
                    raise ValueError("文件不是预期的NOAA天气CSV")

                first = next(reader, None)
                if first is None:
                    raise ValueError("CSV没有数据记录")
                if first["STATION"] != station:
                    raise ValueError("首条记录的站点编号与文件名不一致")

            digest = sha256(part)
            size = part.stat().st_size

            # 只有下载和基本检查通过，才改为正式文件名。
            part.replace(path)

            manifest[station] = {
                "source": "NOAA Global Hourly",
                "station_id": station,
                "filename": path.name,
                "download_url": url,
                "download_started_at_utc": started,
                "downloaded_at": received,
                "bytes": size,
                "sha256": digest,
                "http_status": 200,
                "last_modified": last_modified,
                "etag": etag,
                "last_verified_at_utc": now(),
                "validation": "下载长度、必要字段和首条站点编号通过"
            }
            save_manifest(manifest)

            log({
                "station_id": station,
                "status": "success",
                "attempt": attempt,
                "bytes": size,
                "sha256": digest
            })

            successful += 1
            completed = True
            print(f"下载成功：{size:,} 字节", flush=True)
            break

        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            log({
                "station_id": station,
                "status": "failed_attempt",
                "attempt": attempt,
                "error": message
            })
            print(f"第{attempt}次失败：{message}", flush=True)

            if isinstance(error, urllib.error.HTTPError):
                if error.code in (401, 403, 404):
                    break

            if attempt < 3:
                time.sleep(2 ** attempt)

    if not completed:
        failed.append(station)
        log({"station_id": station, "status": "failed_final"})

    # 控制请求频率。
    time.sleep(1)

print("\n========== 本次下载汇总 ==========")
print(f"计划站点数：{len(station_ids)}")
print(f"新下载成功：{successful}")
print(f"核验后复用：{reused}")
print(f"失败或待核查：{len(failed)}")
if failed:
    print("失败站点：", ", ".join(failed))
print("文件清单：", manifest_path)
print("下载日志：", log_path)
print("本步尚未逐行检查全部日期、月份覆盖和观测类型。")