from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.error
import threading
import hashlib
import json
import csv
import time

project = Path(__file__).resolve().parent.parent
metadata = project / "metadata"
output = project / "data/raw/NOAA/2024"
logs = project / "logs"

for folder in (metadata, output, logs):
    folder.mkdir(parents=True, exist_ok=True)

manifest_path = metadata / "noaa_download_manifest_2024.json"
log_path = logs / "noaa_download_log.jsonl"
lock = threading.Lock()
stop = threading.Event()

def now():
    return datetime.now(timezone.utc).isoformat()

def say(message):
    with lock:
        print(message, flush=True)

def log(data):
    data["logged_at_utc"] = now()
    with lock:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def save_manifest():
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temporary.replace(manifest_path)

with (metadata / "noaa_full_airports_2024.csv").open(
    encoding="utf-8-sig", newline=""
) as f:
    station_ids = sorted({
        r["station_id"] for r in csv.DictReader(f)
    })

if not station_ids or any(
    len(s) != 11 or not s.isalnum() for s in station_ids
):
    raise SystemExit("天气站清单为空或编号格式异常。")

manifest = {}
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

# 工作线程只读取这个快照；文件清单由主线程统一保存。
known_records = dict(manifest)

def download(station):
    path = output / f"{station}.csv"
    part = output / f"{station}.csv.part"
    url = (
        "https://noaa-global-hourly-pds.s3.amazonaws.com/"
        f"2024/{station}.csv"
    )

    if stop.is_set():
        return station, "cancelled", None

    if path.exists():
        known = known_records.get(station, {})
        if (
            known.get("sha256")
            and path.stat().st_size == known.get("bytes")
            and digest(path) == known["sha256"]
        ):
            record = dict(known)
            record["last_verified_at_utc"] = now()
            log({"station_id": station, "status": "verified_existing"})
            say(f"[{station}] 已核验，跳过下载")
            return station, "reused", record

        log({
            "station_id": station,
            "status": "existing_file_not_verified"
        })
        say(f"[{station}] 现有文件未通过核验，保留文件、不覆盖")
        return station, "failed", None

    for attempt in range(1, 4):
        if stop.is_set():
            return station, "cancelled", None

        started = now()
        say(f"[{station}] 正在连接，第{attempt}次尝试")
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

            with urllib.request.urlopen(request, timeout=45) as response:
                length = response.headers.get("Content-Length")
                expected = int(length) if length else None
                last_modified = response.headers.get("Last-Modified")
                etag = response.headers.get("ETag")
                received = 0
                last_report = time.monotonic()

                with part.open("wb") as f:
                    while True:
                        if stop.is_set():
                            return station, "cancelled", None

                        block = response.read(128 * 1024)
                        if not block:
                            break
                        f.write(block)
                        received += len(block)

                        if time.monotonic() - last_report >= 5:
                            progress = (
                                f"{received / expected:.0%}"
                                if expected else "总大小未知"
                            )
                            say(
                                f"[{station}] 已下载 "
                                f"{received / 1_000_000:.2f} MB"
                                f"（{progress}）"
                            )
                            last_report = time.monotonic()

            downloaded_at = now()

            if expected is not None and received != expected:
                raise ValueError("实际下载大小与Content-Length不一致")

            with part.open(encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                fields = set(reader.fieldnames or [])
                if not {"STATION", "DATE", "REPORT_TYPE"}.issubset(fields):
                    raise ValueError("文件不是预期的NOAA天气CSV")
                first = next(reader, None)
                if first is None or first["STATION"] != station:
                    raise ValueError("没有数据或首条站点编号不一致")

            record = {
                "source": "NOAA Global Hourly",
                "station_id": station,
                "filename": path.name,
                "download_url": url,
                "download_started_at_utc": started,
                "downloaded_at": downloaded_at,
                "bytes": part.stat().st_size,
                "sha256": digest(part),
                "http_status": 200,
                "last_modified": last_modified,
                "etag": etag,
                "last_verified_at_utc": now(),
                "validation": "下载长度、必要字段和首条站点编号通过"
            }

            # 主线程负责将临时文件改名，并保存对应清单。
            return station, "downloaded", record

        except Exception as error:
            log({
                "station_id": station,
                "status": "failed_attempt",
                "attempt": attempt,
                "error": f"{type(error).__name__}: {error}"
            })
            say(f"[{station}] 第{attempt}次失败：{error}")

            if isinstance(error, urllib.error.HTTPError):
                if error.code in (401, 403, 404):
                    break

            if attempt < 3:
                if stop.wait(2 ** attempt):
                    return station, "cancelled", None

    log({"station_id": station, "status": "failed_final"})
    return station, "failed", None

counts = {"downloaded": 0, "reused": 0, "failed": 0}
failed = []
completed = 0

say(f"计划检查或下载 {len(station_ids)} 个站点，并行数为2。")

executor = ThreadPoolExecutor(max_workers=2)
futures = {
    executor.submit(download, station): station
    for station in station_ids
}

try:
    for future in as_completed(futures):
        station = futures[future]

        try:
            station, status, record = future.result()
        except Exception as error:
            status, record = "failed", None
            log({
                "station_id": station,
                "status": "worker_failed",
                "error": str(error)
            })

        if status == "cancelled":
            continue

        if status == "downloaded":
            (output / f"{station}.csv.part").replace(
                output / f"{station}.csv"
            )
            manifest[station] = record
            save_manifest()
            log({
                "station_id": station,
                "status": "success",
                "bytes": record["bytes"],
                "sha256": record["sha256"]
            })
            say(f"[{station}] 下载并核验完成")

        elif status == "reused":
            manifest[station] = record
            save_manifest()

        else:
            failed.append(station)

        counts[status] += 1
        completed += 1
        say(
            f"总进度：{completed}/{len(station_ids)}"
            f" | 新下载{counts['downloaded']}"
            f" | 复用{counts['reused']}"
            f" | 失败{counts['failed']}"
        )

except KeyboardInterrupt:
    stop.set()
    say("\n正在停止，请等待当前网络请求退出；已登记的成功文件会保留。")

finally:
    executor.shutdown(wait=True, cancel_futures=True)

print("\n========== 正式采集本次汇总 ==========")
print(f"计划站点数：{len(station_ids)}")
print(f"本次新下载成功：{counts['downloaded']}")
print(f"核验后复用：{counts['reused']}")
print(f"失败或待核查：{counts['failed']}")
print(f"本次未完成：{len(station_ids) - completed}")
if failed:
    print("失败站点：", ", ".join(sorted(failed)))
print("文件清单：", manifest_path)
print("下载日志：", log_path)
print("完成后仍需逐行检查日期、月份覆盖和观测类型。")