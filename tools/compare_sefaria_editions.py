"""Read-only side-by-side Mishnah edition verification through the Sefaria v3 API.

No model calls, no payment, no publication, and no automatic halakhic approval.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://www.sefaria.org/api/v3/texts/Mishnah_Berakhot.1.1"
TITLES = (
    "Torat Emet 357",
    "Mishnah, ed. Romm, Vilna 1913",
    "Mishnah based on the Kaufmann manuscript, edited by Dan Be'eri",
)
MAX_BYTES = 1024 * 1024
PHRASE = re.compile(r"(חייב[יי]ן|חייבים|מותר[יי]ן|מותרים)\s+אתם\s+לקרות")
TAGS = re.compile(r"<[^>]+>")


def clean_text(version):
    raw = version.get("text", [])
    if isinstance(raw, str):
        pieces = [raw]
    elif isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        pieces = raw
    else:
        return ""
    return re.sub(r"\s+", " ", TAGS.sub("", " ".join(pieces))).strip()


def compare(payload):
    report = {
        "reference_requested": "Mishnah Berakhot 1:1",
        "status": "review_required",
        "checked_at_utc": None,  # The GitHub run has an audited timestamp.
        "editions": [],
        "warnings": [],
        "text_locked": False,
        "torah_review_required": True,
        "release_authorized": False,
    }
    if not isinstance(payload, dict) or not isinstance(payload.get("versions"), list):
        report["warnings"].append("Invalid response, missing versions array")
        return report
    ref = payload.get("ref")
    report["reference_returned"] = ref
    if ref != "Mishnah Berakhot 1:1":
        report["warnings"].append("Reference returned differs from requested unit")
    versions = payload["versions"]
    for title in TITLES:
        found = [v for v in versions if isinstance(v, dict) and v.get("versionTitle") == title]
        if len(found) != 1:
            report["warnings"].append("Missing or duplicated edition: " + title)
            report["editions"].append({"title": title, "received": False})
            continue
        version = found[0]
        text = clean_text(version)
        expression = PHRASE.search(text)
        anchor = text.find("אמר להם")
        if anchor < 0:
            anchor = text.find("לא קרינו")
        response_context = text[anchor:anchor + 110] if anchor >= 0 else "unfound"
        ending_context = text[-110:] if text else ""
        flags = {
            "title": title,
            "received": True,
            "license_declared_by_sefaria": version.get("license") or "unknown",
            "source_url": version.get("versionSource") or version.get("versionUrl") or "unknown",
            "word_count": len(text.split()),
            "normalized_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
            "contains_start": "מאימתי" in text or "מאימתיי" in text,
            "contains_gamliel": "רבן גמליאל" in text,
            "contains_sons_story": "בניו" in text and "בית המשתה" in text,
            "contains_final_rationale": "להרחיק" in text and "העבירה" in text,
            "sons_response_token": expression.group(1) if expression else "unresolved",
            "response_context_for_review": response_context,
            "ending_context_for_review": ending_context,
            "content_ready_for_editorial_review": False,
        }
        if flags["word_count"] < 55 or not all(flags[k] for k in ("contains_start", "contains_gamliel", "contains_sons_story", "contains_final_rationale")):
            report["warnings"].append("Possible partial / invalid Mishnah unit in edition: " + title)
        if flags["license_declared_by_sefaria"] not in ("Public Domain", "PD"):
            report["warnings"].append("Non-public-domain or unknown rights: " + title)
        if flags["sons_response_token"] == "unresolved":
            report["warnings"].append("No exact response phrase found in edition: " + title)
        report["editions"].append(flags)
    if len(report["editions"]) == len(TITLES) and not report["warnings"]:
        report["status"] = "three_versions_received_pending_human_review"
    return report


def main():
    output = Path("build/sefaria-variant-comparison.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"status": "unavailable", "warnings": ["Network or API request failed"],
              "text_locked": False, "release_authorized": False, "torah_review_required": True}
    url = BASE + "?" + urlencode([("version", "hebrew|" + title) for title in TITLES] +
                                 [("return_format", "text_only")])
    try:
        request = Request(url, headers={"User-Agent": "MishnahFilmStudioSourceAudit/0.1",
                                       "Accept": "application/json"})
        with urlopen(request, timeout=18) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("API response exceeds safe size")
        report = compare(json.loads(data.decode("utf-8")))
    except Exception as exc:
        report["warnings"] = ["API probe failure type: " + type(exc).__name__]
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("SOURCE AUDIT: " + report["status"])
    for v in report.get("editions", []):
        print("EDITION: " + str(v.get("title")) +
              " | rights=" + str(v.get("license_declared_by_sefaria")) +
              " | words=" + str(v.get("word_count")) +
              " | response=" + str(v.get("sons_response_token")) +
              " | complete=" + str(v.get("contains_final_rationale")))
        if v.get("sons_response_token") == "unresolved" or not v.get("contains_final_rationale"):
            print("REVIEW_CONTEXT: " + str(v.get("response_context_for_review")) +
                  " | END: " + str(v.get("ending_context_for_review")))
    for w in report.get("warnings", []):
        print("WARNING: " + w)
    print("RELEASE: not authorized; human text and Torah review still required")
    return 0  # Network unavailability must not block deterministic offline tests.


if __name__ == "__main__":
    sys.exit(main())
