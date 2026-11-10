# Optional recapture example extracted from data_sources.md.
# Not executed against public servers as part of this supplement.
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import time
import urllib.request
import zipfile

project = Path(__file__).resolve().parent.parent
(project / "logs").mkdir(parents=True, exist_ok=True)
log_path = project / "logs/public_recapture_log.jsonl"

tasks = [
    ("OurAirports/airports.csv", "https://ourairports.com/data/airports.csv"),
    ("NOAA/isd-history.csv", "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"),
    ("Census/cb_2024_us_state_500k.zip",
     "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip")
]
for month in range(1, 13):
    name = f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2024_{month}.zip"
    tasks.append((f"BTS/{name}", "https://transtats.bts.gov/PREZIP/" + name))

for relative, url in tasks:
    destination = project / "data/recaptured" / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print("已存在，保留；如需复核请读取既有日志：", destination)
        continue
    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, 4):
        record = {"url": url, "path": str(destination), "attempt": attempt,
                  "started_at_utc": datetime.now(timezone.utc).isoformat()}
        succeeded = False
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "UniversityCourseResearch/1.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                expected = response.headers.get("Content-Length")
                with temporary.open("wb") as f:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        f.write(block)
            acquired = datetime.now(timezone.utc).isoformat()
            if expected and temporary.stat().st_size != int(expected):
                raise ValueError("Content-Length不一致")
            if destination.suffix == ".zip":
                with zipfile.ZipFile(temporary) as z:
                    if z.testzip() is not None:
                        raise ValueError("ZIP CRC检查失败")
            else:
                import csv
                with temporary.open(encoding="utf-8-sig", newline="") as f:
                    if len(next(csv.reader(f))) < 2:
                        raise ValueError("不是预期CSV")
            with temporary.open("rb") as f:
                checksum = hashlib.file_digest(f, "sha256").hexdigest()
            size = temporary.stat().st_size
            temporary.replace(destination)
            record.update(status="success", acquired_at_utc=acquired,
                          bytes=size, sha256=checksum)
            succeeded = True
        except Exception as error:
            record.update(status="failed_attempt", error=f"{type(error).__name__}: {error}")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(record["status"], relative)
        if succeeded:
            break
        if attempt < 3:
            time.sleep(2 ** attempt)
    time.sleep(1)