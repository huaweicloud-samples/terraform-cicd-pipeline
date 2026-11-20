# -*- coding: utf-8 -*-
"""检查实际 AK/SK 不会落入示例源码、状态、计划或验证结果。"""
from __future__ import annotations

import csv
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS = Path(os.environ.get("CREDENTIALS_CSV", str(ROOT.parents[1] / "credentials.csv")))
SKIP = {".terraform", ".git", "dist", "__pycache__"}


def read_credentials() -> tuple[str, str]:
    with CREDENTIALS.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("credentials.csv has no data rows")
    row = rows[0]
    ak = row.get("Access Key Id", "").strip().strip("\"'")
    sk = row.get("Secret Access Key", "").strip().strip("\"'")
    if not ak or not sk:
        raise SystemExit("credentials.csv is missing the access key columns")
    return ak, sk


def files_to_scan() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP for part in path.parts):
            continue
        if path.resolve() == CREDENTIALS.resolve():
            continue
        files.append(path)
    return files


def main() -> int:
    ak, sk = read_credentials()
    for path in files_to_scan():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for secret in (ak, sk):
            if secret and secret in text:
                raise SystemExit(f"credential value found in {path}")
    print("security scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
