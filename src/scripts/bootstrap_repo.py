# -*- coding: utf-8 -*-
"""将本地示例文件幂等上传到 CodeArts Repo。

凭据只从环境变量读取。脚本只调用仓库文件 API，不触发流水线，也不执行 Terraform。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


AK = os.environ.get("HW_ACCESS_KEY", "")
SK = os.environ.get("HW_SECRET_KEY", "")
REGION = os.environ.get("REGION", "cn-north-4")
REPOSITORY_ID = os.environ.get("REPOSITORY_ID", "")
REPOSITORY_ROOT = Path(os.environ.get("REPOSITORY_ROOT", ".")).resolve()
TARGET_BRANCH = os.environ.get("TARGET_BRANCH", "master")
HOST = f"codehub-ext.{REGION}.myhuaweicloud.com"


def require_environment() -> None:
    missing = [name for name, value in (("HW_ACCESS_KEY", AK), ("HW_SECRET_KEY", SK), ("REPOSITORY_ID", REPOSITORY_ID)) if not value]
    if missing:
        raise RuntimeError("missing required environment configuration: " + ",".join(missing))


def signed_request(method: str, path: str, body: dict, accepted: tuple[int, ...]) -> tuple[int, str]:
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sdk_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    signed = {"content-type": "application/json", "host": HOST, "x-sdk-date": sdk_date}
    canonical_uri = "/" + "/".join(quote(part, safe="") for part in path.strip("/").split("/")) + "/"
    canonical_headers = "".join(f"{key}:{signed[key]}\n" for key in sorted(signed))
    signed_headers = ";".join(sorted(signed))
    canonical_request = "\n".join(
        [method, canonical_uri, "", canonical_headers, signed_headers, hashlib.sha256(payload).hexdigest()]
    )
    string_to_sign = "\n".join(["SDK-HMAC-SHA256", sdk_date, hashlib.sha256(canonical_request.encode()).hexdigest()])
    signature = hmac.new(SK.encode(), string_to_sign.encode(), hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        f"https://{HOST}{path}",
        data=payload,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Sdk-Date": sdk_date,
            "Authorization": f"SDK-HMAC-SHA256 Access={AK}, SignedHeaders={signed_headers}, Signature={signature}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status = response.status
            text = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        status = error.code
        text = error.read().decode("utf-8", "replace")
    if status not in accepted:
        raise RuntimeError(f"Repo API {method} {path} returned HTTP {status}")
    return status, text


def files_to_upload() -> list[tuple[str, Path]]:
    mapping = {
        "README.md": "src/repository/README.md",
        "sample-infra/versions.tf": "src/sample-infra/versions.tf",
        "sample-infra/main.tf": "src/sample-infra/main.tf",
        "sample-infra/variables.tf": "src/sample-infra/variables.tf",
        "sample-infra/outputs.tf": "src/sample-infra/outputs.tf",
    }
    result: list[tuple[str, Path]] = []
    for local_name, repo_path in mapping.items():
        path = REPOSITORY_ROOT / local_name
        if path.is_file():
            result.append((repo_path, path))
    return result


def upload_file(repo_path: str, content: str) -> None:
    body = {
        "file_path": repo_path,
        "branch": TARGET_BRANCH,
        "commit_message": f"bootstrap {repo_path}",
        "content": content,
        "author_name": "terraform-cicd-bootstrap",
        "author_email": "terraform-cicd-bootstrap@example.com",
    }
    create_path = f"/v4/repositories/{REPOSITORY_ID}/repository/files"
    status, _ = signed_request("POST", create_path, body, (200, 201, 400))
    if status in (200, 201):
        print(f"[repo] created path={repo_path}")
        return
    update_path = f"/v4/repositories/{REPOSITORY_ID}/repository/file"
    signed_request("PUT", update_path, body, (200, 201))
    print(f"[repo] updated path={repo_path}")


def main() -> int:
    require_environment()
    files = files_to_upload()
    if not files:
        raise RuntimeError("no repository files found")
    for repo_path, local_path in files:
        upload_file(repo_path, local_path.read_text(encoding="utf-8"))
    print(f"[repo] bootstrap complete files={len(files)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"[repo] bootstrap failed: {error}", file=sys.stderr)
        raise SystemExit(1)
