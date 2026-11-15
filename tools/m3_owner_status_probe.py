"""Owner-private M3 authenticated STATUS probe; no live image dispatch.

Connects only to the candidate gateway's signed /m3/v1/offline route.
Read-only, no retries, no secrets in CLI/logs. This is a diagnostic for
an explicitly deployed private gateway, NOT a deployment or authorization.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "/m3/v1/offline"
OWNER = "barkinam21-pixel"
SCENE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,79}$")


class M3ProbeBlocked(ValueError):
    pass


def prepare_status(scene_id, key_hex, *, timestamp=None):
    if not isinstance(scene_id, str) or not SCENE.fullmatch(scene_id):
        raise M3ProbeBlocked("SCENE_SCOPE_INVALID")
    if not isinstance(key_hex, str) or not re.fullmatch("[a-f0-9]{64}", key_hex):
        raise M3ProbeBlocked("HMAC_KEY_MISSING_OR_INVALID")
    timestamp = timestamp or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    envelope = {"version": 1, "owner": OWNER, "scene_id": scene_id,
                "operation": "status", "payload": {}}
    body = json.dumps(envelope, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    signed = b"POST\n" + ENDPOINT.encode() + b"\n" + timestamp.encode("ascii") + b"\n" + body
    signature = hmac.new(bytes.fromhex(key_hex), signed, hashlib.sha256).hexdigest()
    return body, {"Content-Type": "application/json",
                  "X-M3-Timestamp": timestamp, "X-M3-Signature": signature}


def safe_url(raw):
    try:
        p = urllib.parse.urlsplit(raw)
        if (p.scheme != "https" or not p.hostname
            or p.username or p.password or p.query or p.fragment
            or p.path not in ("", "/") or p.port not in (None, 443)
            or p.hostname in ("localhost", "127.0.0.1")
            or not p.hostname.endswith(".workers.dev")):
            raise M3ProbeBlocked("M3_GATEWAY_HTTPS_WORKERS_DEV_REQUIRED")
        return "https://" + p.hostname + ENDPOINT
    except (ValueError, AttributeError) as exc:
        raise M3ProbeBlocked("M3_GATEWAY_URL_INVALID") from exc


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise M3ProbeBlocked("M3_REDIRECT_DENIED")


def probe_status(url, scene_id, key_hex, *, transport=None):
    endpoint = safe_url(url)
    body, headers = prepare_status(scene_id, key_hex)
    request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    opener = transport or urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=8) as response:
            raw = response.read(8193)
            if len(raw) > 8192:
                raise M3ProbeBlocked("M3_RESPONSE_TOO_LARGE")
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read(8193)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise M3ProbeBlocked("M3_GATEWAY_UNREACHABLE_NO_RETRY") from exc
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise M3ProbeBlocked("M3_GATEWAY_NON_JSON_RESPONSE") from None
    if not isinstance(result, dict):
        raise M3ProbeBlocked("M3_GATEWAY_INVALID_RESPONSE")
    # Do not expose journal contents or authenticated headers in CLI output.
    # A 200 offline status is *not* an executable permit.
    return {"status": "M3_STATUS_READ_ONLY" if status == 200 else "M3_STATUS_BLOCKED",
            "http_status": status, "gateway_status": str(result.get("status", "UNKNOWN"))[:100],
            "live_dispatch_enabled": False, "provider_calls": 0,
            "authorization_to_generate": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-id", default="EP-P07")
    parser.add_argument("--gateway-url", default=os.environ.get("M3_GATEWAY_URL", ""))
    parser.add_argument("--connect", action="store_true",
                        help="Explicitly opt into ONE read-only HTTPS status request")
    args = parser.parse_args(argv)
    if not args.connect:
        print(json.dumps({"status": "DRY_RUN_NO_NETWORK", "provider_calls": 0,
                          "live_dispatch_enabled": False}))
        return 0
    try:
        result = probe_status(args.gateway_url, args.scene_id,
                              os.environ.get("M3_GATEWAY_HMAC_KEY", ""))
        print(json.dumps(result, sort_keys=True))
        return 0 if result["http_status"] == 200 else 2
    except (M3ProbeBlocked, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "provider_calls": 0, "live_dispatch_enabled": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
