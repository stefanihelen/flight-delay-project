"""Shared helpers for member 1's local-only supplementary exports."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def relative(path, root):
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def find_bts_manifest(root):
    """Find one manifest with 12 distinct months and its 12 extracted CSVs."""
    base = Path(root) / "data/raw/BTS"
    candidates = []
    for path in base.rglob("file_manifest.json"):
        data = read_json(path)
        if not isinstance(data, dict) or not isinstance(data.get("files"), list):
            continue
        entries = data["files"]
        months = [entry.get("month") for entry in entries]
        if len(entries) != 12 or set(months) != {f"2024-{m:02d}" for m in range(1, 13)}:
            continue
        for entry in entries:
            member = Path(entry["csv_member"])
            if member.is_absolute() or ".." in member.parts:
                raise ValueError(f"Unsafe CSV member in {path}")
        if all((path.parent / entry["csv_member"]).is_file() for entry in entries):
            candidates.append((path, data))
    if len(candidates) != 1:
        paths = "\n".join(str(path) for path, _ in candidates)
        raise ValueError(
            f"需要恰好一个含12个月解压CSV的BTS manifest，实际找到{len(candidates)}个。"
            "请确认全年ZIP已解压，且没有两套重复解压目录。\n" + paths
        )
    return candidates[0]


def bts_size_audit(root):
    path, data = find_bts_manifest(root)
    entries = data["files"]
    actual_total = 0
    for entry in entries:
        csv_path = path.parent / entry["csv_member"]
        actual = csv_path.stat().st_size
        if actual != int(entry["csv_bytes"]):
            raise ValueError(f"BTS文件大小与清单不符：{csv_path.name}")
        actual_total += actual
    declared = sum(int(entry["csv_bytes"]) for entry in entries)
    if "csv_bytes" in data.get("summary", {}):
        if int(data["summary"]["csv_bytes"]) != declared:
            raise ValueError("BTS manifest的summary与逐月csv_bytes汇总不一致")
    return path, data, actual_total
