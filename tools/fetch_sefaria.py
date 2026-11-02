"""Read-only Sefaria edition probe. Never approves a text or calls a paid service."""
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://www.sefaria.org/api/v3/texts/Mishnah_Berakhot.1.1"
VERSION = "hebrew|Torat Emet 357"
MAX_BYTES = 1024 * 1024


def summarize_source(payload):
    report = {"status": "unverified", "requested_reference": "Mishnah Berakhot 1:1",
              "requested_edition": "Torat Emet 357", "text_locked": False,
              "human_review_required": True}
    if not isinstance(payload, dict):
        report["reason"] = "Unexpected API response type"
        return report
    versions = payload.get("versions", [])
    if not isinstance(versions, list):
        report["reason"] = "Missing versions list"
        return report
    matches = [v for v in versions if isinstance(v, dict) and v.get("versionTitle") == "Torat Emet 357"]
    if len(matches) != 1:
        report["reason"] = "Exact edition not returned; no fallback permitted"
        return report
    match = matches[0]
    raw = match.get("text", [])
    # Sefaria V3 segment response may be one string or an array.
    if isinstance(raw, str):
        parts = [raw]
    elif isinstance(raw, list):
        parts = [x for x in raw if isinstance(x, str)]
    else:
        parts = []
    text = " ".join(parts).strip()
    if not text:
        report["reason"] = "No text returned for requested edition"
        return report
    report.update(status="text_received_pending_human_review",
                  edition=match.get("versionTitle"), license=match.get("license", "unknown"),
                  reference=payload.get("ref", "Mishnah Berakhot 1:1"),
                  sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                  has_maematai="מאימתי" in text or "מאימתיי" in text,
                  has_rabban_gamliel="רבן גמליאל" in text,
                  has_chayavin="חייבין" in text or "חיבין" in text,
                  has_mutarin="מותרין" in text,
                  word_count=len(text.split()), text_locked=False,
                  human_review_required=True)
    if report["license"] != "Public Domain":
        report["status"] = "rights_not_verified"
    return report


def main():
    out = Path("build/sefaria-source-snapshot.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {"status": "unavailable", "requested_edition": "Torat Emet 357",
              "text_locked": False, "human_review_required": True}
    url = BASE + "?" + urlencode({"version": VERSION, "return_format": "text_only"})
    try:
        req = Request(url, headers={"User-Agent": "MishnahFilmStudioResearch/0.1", "Accept": "application/json"})
        with urlopen(req, timeout=15) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("Response too large")
        report = summarize_source(json.loads(data.decode("utf-8")))
    except Exception as exc:
        report["reason"] = type(exc).__name__  # avoid logging request/session data
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report["status"] + " (no approval and no billed generation)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
