from pathlib import Path
from datetime import datetime, timezone
import zipfile
import hashlib
import struct
import json
import csv

project = Path(__file__).resolve().parent.parent
path = (
    project / "data/raw/Census"
    / "cb_2024_us_state_500k.zip"
)
metadata = project / "metadata"
metadata.mkdir(parents=True, exist_ok=True)

if not path.exists():
    raise SystemExit(f"找不到文件：{path}")

with path.open("rb") as f:
    checksum = hashlib.file_digest(f, "sha256").hexdigest()

with zipfile.ZipFile(path) as archive:
    damaged = archive.testzip()
    if damaged:
        raise SystemExit(f"压缩包完整性检查失败：{damaged}")

    names = archive.namelist()
    members = {}

    for extension in (".shp", ".shx", ".dbf", ".prj"):
        matches = [
            n for n in names
            if n.lower().endswith(extension)
        ]
        if len(matches) != 1:
            raise SystemExit(f"{extension}文件缺失或数量异常")
        members[extension] = matches[0]

    projection = archive.read(members[".prj"]).decode("utf-8-sig")
    dbf = archive.read(members[".dbf"])
    shp = archive.read(members[".shp"])
    shx = archive.read(members[".shx"])

    archive_files = [
        {
            "filename": info.filename,
            "uncompressed_bytes": info.file_size,
            "compressed_bytes": info.compress_size,
            "crc32": f"{info.CRC:08x}"
        }
        for info in archive.infolist()
        if not info.is_dir()
    ]

# 读取DBF属性表结构。
declared_count = struct.unpack_from("<I", dbf, 4)[0]
header_length, record_length = struct.unpack_from("<HH", dbf, 8)

if len(dbf) < header_length + declared_count * record_length:
    raise SystemExit("DBF长度不足，可能存在文件损坏。")

fields = []
position = 32

while position < header_length and dbf[position] != 13:
    descriptor = dbf[position:position + 32]
    name = descriptor[:11].split(b"\x00")[0].decode("ascii")
    length = descriptor[16]
    fields.append((name, length))
    position += 32

field_names = [name for name, length in fields]
required = {"STATEFP", "STUSPS", "NAME", "GEOID"}

if not required.issubset(field_names):
    raise SystemExit("州界属性表缺少必要关联字段。")

states = []
deleted_count = 0

for index in range(declared_count):
    start = header_length + index * record_length
    record = dbf[start:start + record_length]

    if record[0:1] == b"*":
        deleted_count += 1
        continue
    if record[0:1] != b" ":
        raise SystemExit("发现异常DBF记录标记。")

    row = {}
    offset = 1
    for name, length in fields:
        value = record[offset:offset + length]
        row[name] = value.decode("utf-8").strip()
        offset += length

    states.append({
        key: row[key]
        for key in ("STATEFP", "STUSPS", "NAME", "GEOID")
    })

# 检查Shapefile头部及索引数量。
file_code = struct.unpack_from(">i", shp, 0)[0]
declared_shp_bytes = struct.unpack_from(">i", shp, 24)[0] * 2
shape_type = struct.unpack_from("<i", shp, 32)[0]
bounds = struct.unpack_from("<4d", shp, 36)

if file_code != 9994 or declared_shp_bytes != len(shp):
    raise SystemExit("SHP文件头或文件长度异常。")

if len(shx) < 100 or (len(shx) - 100) % 8 != 0:
    raise SystemExit("SHX索引文件长度异常。")

index_count = (len(shx) - 100) // 8
if index_count != declared_count:
    raise SystemExit("SHX索引数量与DBF记录数不一致。")

result = {
    "source": "U.S. Census Bureau",
    "dataset": "2024 State and Equivalent Entities 1:500,000",
    "download_url":
        "https://www2.census.gov/geo/tiger/GENZ2024/shp/"
        "cb_2024_us_state_500k.zip",
    "filename": path.name,
    "zip_bytes": path.stat().st_size,
    "sha256": checksum,
    "zip_crc_check": "passed",
    "archive_files": archive_files,
    "dbf_declared_records": declared_count,
    "active_records": len(states),
    "deleted_records": deleted_count,
    "shx_index_records": index_count,
    "dbf_fields": field_names,
    "shape_type": shape_type,
    "bounds": list(bounds),
    "projection_wkt": projection,
    "states": states,
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "downloaded_at": None
}

inventory_path = metadata / "census_state_inventory.json"
inventory_path.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

with (metadata / "census_states_2024.csv").open(
    "w", encoding="utf-8-sig", newline=""
) as f:
    writer = csv.DictWriter(
        f, fieldnames=["STATEFP", "STUSPS", "NAME", "GEOID"]
    )
    writer.writeheader()
    writer.writerows(states)

print("ZIP完整性检查：通过")
print(f"ZIP大小：{path.stat().st_size:,} 字节")
print(f"SHA-256：{checksum}")
print(f"州及州级等同地区有效记录数：{len(states)}")
print(f"DBF删除标记记录数：{deleted_count}")
print(f"SHX索引记录数：{index_count}")
print(f"关联字段检查：通过，包含 {sorted(required)}")
print(f"几何类型编号：{shape_type}（5表示Polygon）")
print(f"坐标系原始说明：\n{projection}")
print(f"\n检查记录已保存：{inventory_path}")
print("州代码清单已保存：metadata/census_states_2024.csv")