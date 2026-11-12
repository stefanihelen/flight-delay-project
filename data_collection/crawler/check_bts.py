from pathlib import Path
from tkinter import Tk, filedialog
import hashlib
import json

root = Tk()
root.withdraw()

folder = filedialog.askdirectory(
    title="请选择包含12个月CSV和file_manifest.json的文件夹"
)
root.destroy()

if not folder:
    raise SystemExit("未选择文件夹，检查已取消。")

folder = Path(folder)
manifest_path = folder / "file_manifest.json"

if not manifest_path.exists():
    raise SystemExit("没有找到file_manifest.json，请选择解压后的数据文件夹。")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
files = manifest["files"]

if len(files) != 12:
    raise SystemExit("文件清单不是12个月，请检查。")

passed = 0

for item in files:
    path = folder / item["csv_member"]

    if not path.exists():
        print(f'{item["month"]}：文件缺失')
        continue

    with path.open("rb") as f:
        actual_hash = hashlib.file_digest(f, "sha256").hexdigest()

    size_ok = path.stat().st_size == item["csv_bytes"]
    hash_ok = actual_hash == item["csv_sha256"]

    if size_ok and hash_ok:
        passed += 1
        print(f'{item["month"]}：大小和SHA-256均通过')
    else:
        print(f'{item["month"]}：校验失败')

print(f"\n检查完成：{passed}/12个月通过。")

if passed == 12:
    total = sum(item["records"] for item in files)
    print(f"清单登记的全年航班记录数：{total:,}条")
    print("注意：本次核对文件大小和校验值，没有重新统计CSV行数。")