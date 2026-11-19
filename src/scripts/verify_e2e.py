# -*- coding: utf-8 -*-
"""触发并核对 CodeArts 四阶段流水线；本脚本不会执行 Terraform apply。

两个销毁阶段的分工（本脚本只验证、不执行任何销毁）：

1. 流水线 Destroy 阶段：验证过程中由流水线执行，只清理 `sample-infra/`
   下的演示资源（示例 LTS 日志组）及流水线状态对象；本脚本随后断言
   示例日志组已不存在（sample_lts_absent）。
2. 根流水线栈（CodeArts 项目/Repo/构建任务/流水线与 OBS 工具链桶）：
   验证结束后必须保留，由人工在根工程执行 `terraform destroy` 统一销毁；
   本脚本不会触碰根栈。
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[2]
TERRAFORM = os.environ.get("TERRAFORM", "/tmp/terraform.exe")
REGION = os.environ.get("REGION", "cn-north-4")
CREDENTIALS = Path(os.environ.get("CREDENTIALS_CSV", str(ROOT.parents[1] / "credentials.csv")))
PIPELINE_HOST = f"cloudpipeline-ext.{REGION}.myhuaweicloud.com"
BUILD_HOST = f"cloudbuild-ext.{REGION}.myhuaweicloud.com"
LTS_HOST = f"lts.{REGION}.myhuaweicloud.com"


def read_credentials() -> tuple[str, str]:
    with CREDENTIALS.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError("credentials.csv has no data rows")
    row = rows[0]
    ak = row.get("Access Key Id", "").strip().strip("\"'")
    sk = row.get("Secret Access Key", "").strip().strip("\"'")
    if not ak or not sk:
        raise RuntimeError("credentials.csv is missing the access key columns")
    return ak, sk


def tf_outputs() -> dict:
    result = subprocess.run([TERRAFORM, "output", "-json"], cwd=ROOT, capture_output=True, check=True)
    return json.loads(result.stdout.decode("utf-8", "replace"))


def api(
    ak: str,
    sk: str,
    host: str,
    method: str,
    path: str,
    query: list[tuple[str, str]] | None = None,
    body: dict | None = None,
    accepted: tuple[int, ...] = (200, 201, 202, 204),
) -> tuple[int, str]:
    query = query or []
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8") if body is not None else b""
    sdk_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    signed = {"content-type": "application/json", "host": host, "x-sdk-date": sdk_date}
    canonical_uri = "/" + "/".join(quote(part, safe="") for part in path.strip("/").split("/")) + "/"
    canonical_query = urllib.parse.urlencode(sorted(query), quote_via=urllib.parse.quote)
    signed_headers = ";".join(sorted(signed))
    canonical_headers = "".join(f"{key}:{signed[key]}\n" for key in sorted(signed))
    canonical_request = "\n".join(
        [method, canonical_uri, canonical_query, canonical_headers, signed_headers, hashlib.sha256(payload).hexdigest()]
    )
    string_to_sign = "\n".join(["SDK-HMAC-SHA256", sdk_date, hashlib.sha256(canonical_request.encode()).hexdigest()])
    signature = hmac.new(sk.encode(), string_to_sign.encode(), hashlib.sha256).hexdigest()
    url = f"https://{host}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url,
        data=payload if method in ("POST", "PUT", "PATCH") else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Sdk-Date": sdk_date,
            "Authorization": f"SDK-HMAC-SHA256 Access={ak}, SignedHeaders={signed_headers}, Signature={signature}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status, text = response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        status, text = error.code, error.read().decode("utf-8", "replace")
    if status not in accepted:
        raise RuntimeError(f"{method} {path} returned HTTP {status}")
    return status, text


def json_api(*args, **kwargs) -> dict:
    _, text = api(*args, **kwargs)
    return json.loads(text) if text else {}


def payload_dict(payload: dict) -> dict:
    nested = payload.get("result") if isinstance(payload, dict) else None
    if isinstance(nested, dict) and any(key in nested for key in ("status", "stages", "pipeline_runs")):
        return nested
    return payload


def pipeline_run_id(payload: dict) -> str | None:
    candidates = [payload]
    if isinstance(payload.get("result"), dict):
        candidates.append(payload["result"])
    for candidate in candidates:
        run_id = candidate.get("pipeline_run_id") or candidate.get("id")
        if run_id:
            return str(run_id)
    return None


def find_pipeline_run_id(ak: str, sk: str, outputs: dict, token: str, timeout: int = 180) -> str:
    project_id = outputs["project_id"]["value"]
    pipeline_id = outputs["pipeline_id"]["value"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        listed = json_api(
            ak,
            sk,
            PIPELINE_HOST,
            "POST",
            f"/v5/{project_id}/api/pipelines/{pipeline_id}/pipeline-runs/list",
            body={"offset": 0, "limit": 20},
        )
        if isinstance(listed.get("result"), dict):
            listed = listed["result"]
        items = listed.get("pipeline_runs") or listed.get("items") or []
        if isinstance(items, dict):
            items = items.get("pipeline_runs") or items.get("items") or []
        for item in items:
            candidate_id = item.get("pipeline_run_id") or item.get("id")
            if not candidate_id:
                continue
            try:
                detail = payload_dict(
                    json_api(
                        ak,
                        sk,
                        PIPELINE_HOST,
                        "GET",
                        f"/v5/{project_id}/api/pipelines/{pipeline_id}/pipeline-runs/detail",
                        query=[("pipeline_run_id", str(candidate_id))],
                    )
                )
            except RuntimeError:
                continue
            if token in json.dumps(detail, ensure_ascii=False):
                return str(candidate_id)
        time.sleep(5)
    raise RuntimeError("pipeline run response did not contain a matching run ID")


def run_pipeline(ak: str, sk: str, outputs: dict) -> str:
    project_id = outputs["project_id"]["value"]
    pipeline_id = outputs["pipeline_id"]["value"]
    repository_id = outputs["repository_id"]["value"]
    token = f"e2e-{int(time.time())}"
    body = {
        "sources": [{
            "type": "code",
            "params": {
                "codehub_id": repository_id,
                "git_type": "codehub",
                "git_url": outputs["repository_url"]["value"],
                "default_branch": "master",
                "build_params": {"build_type": "branch", "event_type": "Manual", "target_branch": "master"},
            },
        }],
        "choose_stages": ["stage_validate", "stage_plan", "stage_apply", "stage_destroy"],
        "choose_jobs": ["JOB_validate", "JOB_plan", "JOB_apply", "JOB_destroy"],
        "description": token,
    }
    response = json_api(
        ak,
        sk,
        PIPELINE_HOST,
        "POST",
        f"/v5/{project_id}/api/pipelines/{pipeline_id}/run",
        body=body,
    )
    return pipeline_run_id(response) or find_pipeline_run_id(ak, sk, outputs, token)


def wait_pipeline(ak: str, sk: str, outputs: dict, run_id: str, timeout: int = 1800) -> dict:
    project_id = outputs["project_id"]["value"]
    pipeline_id = outputs["pipeline_id"]["value"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        detail = payload_dict(
            json_api(
                ak,
                sk,
                PIPELINE_HOST,
                "GET",
                f"/v5/{project_id}/api/pipelines/{pipeline_id}/pipeline-runs/detail",
                query=[("pipeline_run_id", run_id)],
            )
        )
        status = detail.get("status")
        print(f"[pipeline] run_id={run_id} status={status}", flush=True)
        if status in ("COMPLETED", "FAILED"):
            return detail
        time.sleep(20)
    raise RuntimeError("pipeline run polling timed out")


def flatten_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return ""


def stage_build_invocations(detail: dict) -> dict[str, list[dict[str, str]]]:
    result = {"validate": [], "plan": [], "apply": [], "destroy": []}
    for stage in detail.get("stages") or []:
        stage_text = " ".join((str(stage.get(key, "")) for key in ("name", "identifier"))).lower()
        key = next((candidate for candidate in result if candidate in stage_text), None)
        if not key:
            continue
        for job in stage.get("jobs") or []:
            for step in job.get("steps") or []:
                inputs = {
                    str(item.get("key")): str(item.get("value"))
                    for item in step.get("inputs") or []
                    if isinstance(item, dict) and item.get("key") is not None
                }
                job_id = inputs.get("jobId")
                daily_build_number = step.get("daily_build_number")
                if not job_id or not daily_build_number:
                    continue
                build_no = str(daily_build_number).rsplit(".", 1)[-1]
                if build_no.isdigit():
                    result[key].append({"job_id": job_id, "build_no": build_no})
    return result


def build_log(ak: str, sk: str, job_id: str, build_no: str) -> str:
    record = json_api(ak, sk, BUILD_HOST, "GET", f"/v4/jobs/{job_id}/{build_no}/record-info")
    record = record.get("result") or record
    record_id = record.get("build_record_id")
    if not record_id:
        raise RuntimeError("build record response has no build_record_id")
    _, log = api(ak, sk, BUILD_HOST, "GET", f"/v4/{record_id}/download-log")
    return log


def redact(text: str, ak: str, sk: str) -> str:
    return text.replace(ak, "[REDACTED]").replace(sk, "[REDACTED]")


def verify_stage_logs(ak: str, sk: str, detail: dict) -> dict[str, dict]:
    expected = {"validate": "VALIDATE_OK", "plan": "PLAN_OK", "apply": "APPLY_OK", "destroy": "DESTROY_OK"}
    invocations = stage_build_invocations(detail)
    checks: dict[str, dict] = {}
    for stage, marker in expected.items():
        invocation = invocations[stage][0] if invocations[stage] else None
        check = {"marker": marker, "found": False, "evidence": []}
        if invocation:
            check.update(invocation)
            try:
                log = build_log(ak, sk, invocation["job_id"], invocation["build_no"])
                lines = [redact(line[:500], ak, sk) for line in log.splitlines() if marker in line]
                check["found"] = bool(lines)
                check["evidence"] = lines[:3]
            except Exception as error:
                check["error"] = str(error)[:200]
        else:
            check["error"] = "pipeline detail has no Build step metadata"
        checks[stage] = check
    return checks


def verify_lts_absent(ak: str, sk: str, outputs: dict) -> bool:
    project_id = outputs["project_id"]["value"]
    group_name = outputs["sample_log_group_name"]["value"]
    _, text = api(ak, sk, LTS_HOST, "GET", f"/v2/{project_id}/groups", query=[("limit", "100")])
    payload = json.loads(text) if text else {}
    if isinstance(payload.get("result"), dict):
        payload = payload["result"]
    groups = payload.get("log_groups") or payload.get("groups") or payload.get("items") or []
    return not any(
        isinstance(group, dict) and (group.get("group_name") or group.get("name")) == group_name
        for group in groups
    )


DESTROY_PHASE_NOTE = {
    "pipeline_destroy_stage": "流水线 Destroy 阶段只清理 sample-infra/ 演示资源（示例 LTS 日志组）与流水线状态对象",
    "root_stack_destroy": "根流水线栈（CodeArts/OBS/构建任务）验证后保留，最后由人工在根工程执行 terraform destroy 统一销毁",
}


def main() -> int:
    ak, sk = read_credentials()
    outputs = tf_outputs()
    run_id = run_pipeline(ak, sk, outputs)
    detail = wait_pipeline(ak, sk, outputs, run_id)
    log_checks = verify_stage_logs(ak, sk, detail)
    checks = {
        "pipeline_completed": detail.get("status") == "COMPLETED",
        "stage_log_markers": all(item["found"] for item in log_checks.values()),
        # 注意：这里验证的是流水线 Destroy 阶段对 sample-infra 演示资源的清理，
        # 根流水线栈不在该检查范围，需验证完成后另行统一销毁。
        "sample_lts_absent": verify_lts_absent(ak, sk, outputs),
    }
    result = {
        "run_id": run_id,
        "pipeline_status": detail.get("status"),
        "stage_status": {
            str(stage.get("identifier") or stage.get("name")): stage.get("status")
            for stage in detail.get("stages") or []
        },
        "log_checks": log_checks,
        "checks": checks,
        "destroy_phases": DESTROY_PHASE_NOTE,
        "passed": all(checks.values()),
    }
    (ROOT / "verify-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("[verify] 提醒：流水线 Destroy 阶段只清理 sample-infra 演示资源；"
          "根流水线栈请在验证完成后于根工程执行 terraform destroy 统一销毁。")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"[verify] failed: {error}", file=sys.stderr)
        raise SystemExit(1)
