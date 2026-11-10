"""Read-only Modal account visibility audit, never GPU readiness authorization.

Only calls `modal app list --json` and `modal billing summary --json`.
Raw command output and errors are NEVER printed or written to a report: they
might contain private workspace data. A successful auth check is not permission
for model deployment, reference upload, GPU work, or any external spending.
"""
import json
import os
import subprocess
import sys

EXPECTED_APP = "mishnah-flux2-klein4b"
COMMANDS = (
    ("apps", ("modal", "app", "list", "--json")),
    ("billing", ("modal", "billing", "summary", "--json")),
)


def _read_only_json(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None, "UNAVAILABLE"
    if result.returncode != 0:
        return None, "COMMAND_FAILED"
    try:
        return json.loads(result.stdout), "READABLE"
    except (ValueError, TypeError):
        return None, "INVALID_JSON"


def _listed_app_names(document):
    """Only explicit name/app_name keys count; never infer deployment status."""
    names = set()
    def visit(node):
        if isinstance(node, dict):
            for key in ("name", "app_name"):
                if isinstance(node.get(key), str):
                    names.add(node[key])
            for val in node.values():
                if isinstance(val, (dict, list)):
                    visit(val)
        elif isinstance(node, list):
            for val in node:
                visit(val)
    visit(document)
    return names


def audit():
    report = {
        "audit": "modal_readonly_preflight_v1",
        "status": "BLOCKED_NO_GPU_AUTHORIZATION",
        "credentials_present": bool(os.environ.get("MODAL_TOKEN_ID") and
                                    os.environ.get("MODAL_TOKEN_SECRET")),
        "app_list": "NOT_RUN",
        "expected_app_visible": None,
        "billing_summary": "NOT_RUN",
        "authenticated_account_verified": False,
        "deployed_gpu_verified": False,
        "hard_spend_cap_verified": False,
        "private_reference_runtime_verified": False,
        "reference_transfer_approved": False,
        "gpu_execution_authorized": False,
        "modal_gpu_requests": 0,
        "account_charges": "unknown",
        "workspace_usage": "unknown",
    }
    if not report["credentials_present"]:
        report["status"] = "BLOCKED_MISSING_CREDENTIALS"
        return report
    apps, app_status = _read_only_json(COMMANDS[0][1])
    report["app_list"] = app_status
    report["authenticated_account_verified"] = app_status == "READABLE"
    if app_status == "READABLE":
        report["expected_app_visible"] = EXPECTED_APP in _listed_app_names(apps)
    _billing, billing_status = _read_only_json(COMMANDS[1][1])
    report["billing_summary"] = billing_status
    # Billing access does NOT prove any free credits remain, or a hard cap.
    # Neither successful call tests deployment, model execution or privacy.
    return report


def main():
    report = audit()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["credentials_present"] else 2


if __name__ == "__main__":
    sys.exit(main())
