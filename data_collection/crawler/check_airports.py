from pathlib import Path
from tkinter import Tk, filedialog
from datetime import datetime, timezone
import csv
import hashlib
import json

root = Tk()
root.withdraw()
selected = filedialog.askopenfilename(
    title="请选择刚下载的 airports.csv",
    filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")]
)
root.destroy()

if not selected:
    raise SystemExit("未选择文件，检查已取消。")

path = Path(selected)

with path.open("rb") as f:
    checksum = hashlib.file_digest(f, "sha256").hexdigest()

required = {
    "ident", "name", "iata_code", "iso_country",
    "latitude_deg", "longitude_deg"
}

with path.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames or []
    missing = required - set(fields)

    if missing:
        raise SystemExit(f"缺少必要字段：{sorted(missing)}，请检查下载文件。")

    count = 0
    us_count = 0
    for row in reader:
        count += 1
        if row["iso_country"] == "US":
            us_count += 1

result = {
    "source": "OurAirports",
    "source_page": "https://ourairports.com/data/",
    "download_url": "https://ourairports.com/data/airports.csv",
    "filename": path.name,
    "bytes": path.stat().st_size,
    "sha256": checksum,
    "records": count,
    "us_records": us_count,
    "fields": fields,
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "downloaded_at": None
}

project = Path(__file__).resolve().parent.parent
output = project / "metadata" / "ourairports_inventory.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("必要字段检查通过。")
print(f"总记录数：{count:,}")
print(f"iso_country为US的记录数：{us_count:,}")
print(f"文件大小：{result['bytes']:,} 字节")
print(f"SHA-256：{checksum}")
print(f"检查记录已保存到：{output}")