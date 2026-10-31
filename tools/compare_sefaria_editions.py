"""Read-only side-by-side Mishnah edition verification through the Sefaria v3 API.

No model calls, no payment, no publication, and no automatic halakhic approval.
"""
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

BASE = "https://www.sefaria.org/api/v3/texts/Mishnah_Berakhot.1.1"
TEXT_URL = "https://www.sefaria.org/Mishnah_Berakhot.1.1"
TITLES = (
    "Torat Emet 357",
    "Mishnah, ed. Romm, Vilna 1913",
    "Mishnah based on the Kaufmann manuscript, edited by Dan Be'eri",
)
MAX_BYTES = 1024 * 1024
PHRASE = re.compile(r"(חייבין|חיבין|חייבים|חיבים|מותרין|מתרין|מותרים|מתרים)\s+אתם\s+לקרות")
KNOWN_PUBLIC_DOMAIN = {"public domain", "pd"}
UNIT_MARKERS = {
    "evening_shema_start": "שאלה על תחילת זמן קריאת שמע בערבית",
    "eliezers_first_watch": "דעת רבי אליעזר עד סוף האשמורה הראשונה",
    "sages_midnight": "דעת חכמים עד חצות",
    "gamliel_dawn": "דעת רבן גמליאל עד עמוד השחר",
    "sons_at_banquet": "מעשה הבנים החוזרים מבית המשתה",
    "sons_response_variant": "תשובת חייבין/מותרין אתם לקרות",
    "lo_zo_bilvad": "המשך לשון לא זו בלבד",
    "burning_fats_and_limbs": "הקטר חלבים ואברים עד עמוד השחר",
    "preventive_midnight_rationale": "הטעם להרחיק את האדם מן העבירה",
}


def clean_text(version):
    raw = version.get("text", [])
    if isinstance(raw, str):
        pieces = [raw]
    elif isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        pieces = raw
    else:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", " ".join(pieces))).strip()


def normalized_for_matching(text):
    """Remove niqqud/cantillation only for comparison; preserve source text and hash."""
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def _normalized_with_source_positions(text):
    normalized = []
    positions = []
    for source_position, character in enumerate(text):
        for normalized_character in unicodedata.normalize("NFD", character):
            if unicodedata.category(normalized_character) != "Mn":
                normalized.append(normalized_character)
                positions.append(source_position)
    return "".join(normalized), positions


def whole_unit_markers(text):
    return {
        "evening_shema_start": (
            any(word in text for word in ("מאימתי", "מאימתיי", "מאמתי", "מאמתיי"))
            and "שמע" in text
            and any(word in text for word in ("בערבית", "בערבין"))
        ),
        "eliezers_first_watch": (
            "אליעזר" in text
            and any(word in text for word in ("האשמורה", "האשמורת"))
            and "ראשונה" in text
        ),
        "sages_midnight": "חכמים" in text and "חצות" in text,
        "gamliel_dawn": "רבן גמליאל" in text and "עמוד השחר" in text,
        "sons_at_banquet": (
            "בניו" in text and "בית המשתה" in text
            and any(word in text for word in ("אמר להם", "אמר להן"))
            and "לא קרינו את שמע" in text
        ),
        "sons_response_variant": PHRASE.search(text) is not None,
        "lo_zo_bilvad": "לא זו בלבד" in text,
        "burning_fats_and_limbs": (
            "הקטר" in text
            and any(word in text for word in ("חלבים", "חלבין"))
            and any(word in text for word in ("אברים", "איברים"))
            and "עמוד השחר" in text
        ),
        "preventive_midnight_rationale": (
            "חכמים" in text and "חצות" in text and "להרחיק" in text
            and any(word in text for word in ("העבירה", "עברה"))
        ),
    }


def _base_report():
    return {
        "schema_version": 2,
        "reference_requested": "Mishnah Berakhot 1:1",
        "status": "review_required",
        "checked_at_utc": None,
        "editions": [],
        "warnings": [],
        "unit_markers": dict(UNIT_MARKERS),
        "text_locked": False,
        "text_verified": False,
        "textual_variants_reviewed": False,
        "rights_reviewed": False,
        "torah_review_required": True,
        "torah_approved": False,
        "release_authorized": False,
    }


def _edition_url(title):
    return TEXT_URL + "?" + urlencode({"version": "hebrew|" + title})


def _safe_source_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return value


def _source_span(text, positions, start, end):
    if start >= len(positions) or end <= start:
        return ""
    original_start = positions[start]
    original_end = positions[end - 1] + 1
    while original_end < len(text) and unicodedata.category(text[original_end]) == "Mn":
        original_end += 1
    return text[original_start:original_end]


def _excerpt(text, positions, match):
    if match is None or not positions:
        return ""
    original_start = positions[match.start()]
    original_end = positions[match.end() - 1] + 1
    start = max(0, original_start - 35)
    end = min(len(text), original_end + 35)
    return text[start:end]


def _empty_edition(title):
    return {
        "title": title,
        "received": False,
        "license_declared_by_sefaria": "unknown",
        "edition_url": _edition_url(title),
        "source_url": None,
        "word_count": 0,
        "source_text_sha256": None,
        "normalized_text_sha256": None,
        "coverage": {key: False for key in UNIT_MARKERS},
        "sons_response_token": "unresolved",
        "sons_response_original": "unresolved",
        "sons_response_meaning": "unresolved",
        "comparison_excerpt": "",
        "full_text_included": False,
        "full_text": None,
        "content_ready_for_editorial_review": False,
        "reviewer_required": True,
        "rights_review_required": True,
        "text_verified": False,
        "torah_approved": False,
        "release_authorized": False,
    }


def compare(payload):
    report = _base_report()
    if not isinstance(payload, dict) or not isinstance(payload.get("versions"), list):
        report["warnings"].append("Invalid response, missing versions array")
        report["editions"] = [_empty_edition(title) for title in TITLES]
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
            report["editions"].append(_empty_edition(title))
            continue

        version = found[0]
        text = clean_text(version)
        normalized, positions = _normalized_with_source_positions(text)
        phrase_match = PHRASE.search(normalized)
        original_excerpt = _excerpt(text, positions, phrase_match)
        response_token = phrase_match.group(1) if phrase_match else "unresolved"
        response_original = (
            _source_span(text, positions, *phrase_match.span(1))
            if phrase_match else "unresolved"
        )
        license_name = version.get("license") or "unknown"
        known_public_domain = str(license_name).strip().casefold() in KNOWN_PUBLIC_DOMAIN
        coverage = whole_unit_markers(normalized)
        meaning = (
            "obligation" if response_token.startswith(("ח",))
            else "permission" if response_token.startswith(("מ",))
            else "unresolved"
        )
        item = {
            "title": title,
            "received": True,
            "license_declared_by_sefaria": license_name,
            "edition_url": _edition_url(title),
            "source_url": _safe_source_url(
                version.get("versionSource") or version.get("versionUrl")
            ),
            "word_count": len(text.split()),
            "source_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
            "normalized_text_sha256": (
                hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None
            ),
            "coverage": coverage,
            "sons_response_token": response_token,
            "sons_response_original": response_original,
            "sons_response_meaning": meaning,
            "comparison_excerpt": original_excerpt,
            "full_text_included": bool(text and known_public_domain),
            "full_text": text if text and known_public_domain else None,
            "content_ready_for_editorial_review": False,
            "reviewer_required": True,
            "rights_review_required": True,
            "text_verified": False,
            "torah_approved": False,
            "release_authorized": False,
        }
        if item["word_count"] < 55 or not all(coverage.values()):
            report["warnings"].append("Possible partial / invalid Mishnah unit in edition: " + title)
        if not known_public_domain:
            report["warnings"].append("Non-public-domain or unknown rights: " + title)
        if response_token == "unresolved":
            report["warnings"].append("No exact response phrase found in edition: " + title)
        report["editions"].append(item)

    if len(report["editions"]) == len(TITLES) and not report["warnings"]:
        report["status"] = "three_versions_received_pending_human_review"
    return report


def audit_ok(report):
    """Only API evidence completeness; NEVER Torah/release approval."""
    return (
        isinstance(report, dict)
        and report.get("status") == "three_versions_received_pending_human_review"
        and not report.get("warnings")
        and len(report.get("editions", [])) == len(TITLES)
        and all(e.get("received") for e in report.get("editions", []))
        and report.get("text_locked") is False
        and report.get("torah_approved") is False
        and report.get("release_authorized") is False
    )


def render_html(report):
    """Render a standalone RTL report; API strings are always escaped before HTML output."""
    editions = report.get("editions", [])
    headings = "".join(
        '<th scope="col"><a href="{}">{}</a></th>'.format(
            html.escape(_edition_url(title), quote=True), html.escape(title)
        )
        for title in TITLES
    )

    def row(label, value_for):
        cells = "".join("<td>{}</td>".format(value_for(item)) for item in editions)
        return "<tr><th scope=\"row\">{}</th>{}</tr>".format(html.escape(label), cells)

    def link_for(item):
        source_link = ""
        if item.get("source_url"):
            href = html.escape(item["source_url"], quote=True)
            source_link = ' <a href="{}">פרטי מקור</a>'.format(href)
        return '<a href="{}">קישור למהדורה</a>{}'.format(
            html.escape(item.get("edition_url", ""), quote=True), source_link
        )

    def text_for(item):
        if item.get("full_text_included") and item.get("full_text"):
            return "<details><summary>הצגת היחידה המלאה (רישיון PD לפי ספריא)</summary>" \
                   '<bdi dir="rtl">{}</bdi></details>'.format(html.escape(item["full_text"]))
        excerpt = item.get("comparison_excerpt") or "לא התקבל קטע להשוואה"
        note = "הטקסט המלא הושמט: הרישיון אינו ידוע או אינו נחלת הכלל."
        return "<bdi dir=\"rtl\">{}</bdi><p>{}</p>".format(
            html.escape(excerpt), html.escape(note)
        )

    def coverage_for(item):
        return "".join(
            '<li class="{}">{}</li>'.format(
                "pass" if item.get("coverage", {}).get(key) else "missing",
                html.escape(description),
            )
            for key, description in UNIT_MARKERS.items()
        )

    table_rows = "".join([
        row("קישור מדויק", link_for),
        row("רישיון לפי מטא־נתוני ספריא", lambda item: html.escape(
            str(item.get("license_declared_by_sefaria", "unknown"))
        )),
        row("הנוסח בתשובה (ללא הכרעה)", lambda item: (
            '<bdi dir="rtl">{}</bdi> — {}'.format(
                html.escape(str(item.get("sons_response_original", "unresolved"))),
                html.escape(str(item.get("sons_response_meaning", "unresolved"))),
            )
        )),
        row("השוואה", text_for),
        row("כיסוי תשעת רכיבי היחידה", lambda item: "<ul>{}</ul>".format(coverage_for(item))),
        row("SHA-256 נוסח המקור", lambda item: "<code>{}</code>".format(
            html.escape(str(item.get("source_text_sha256") or "לא זמין"))
        )),
        row("בדיקת ביקורת נדרשת", lambda item: "כן" if item.get("reviewer_required") else "לא"),
    ])
    warnings = "".join("<li>{}</li>".format(html.escape(str(w))) for w in report.get("warnings", []))
    if not warnings:
        warnings = "<li>אין אזהרות טכניות; נדרשת ביקורת אנושית.</li>"
    return """<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>השוואת מהדורות — ברכות א׳, א׳</title>
<style>
body{{font-family:system-ui,sans-serif;line-height:1.6;margin:1rem;color:#1d2630}}
h1,h2{{line-height:1.25}} .notice{{background:#fff3cd;padding:.8rem;border-inline-start:4px solid #d39e00}}
.table-wrap{{overflow-x:auto}} table{{border-collapse:collapse;min-width:900px;width:100%}}
th,td{{border:1px solid #aeb8c2;padding:.65rem;vertical-align:top;text-align:right}}
thead th{{background:#e8eef4}} td ul{{padding-inline-start:1.2rem;margin:.2rem 0}}
.pass{{color:#176b35}} .missing{{color:#9c1c1c}} code{{overflow-wrap:anywhere}}
details{{max-width:38rem}} bdi{{unicode-bidi:isolate}}
</style>
</head>
<body>
<h1>השוואת מהדורות: משנה ברכות א׳, א׳</h1>
<p class="notice"><strong>דוח מחקר טכני בלבד.</strong> השוואת נוסח ורישיונות אינה הכרעה תורנית,
אישור זכויות, נעילת נוסח או אישור לפרסום. כל דגלי האישור נשארים שקריים.</p>
<p>מצב: <bdi dir="ltr">{status}</bdi>. תאריך בדיקה: <bdi dir="ltr">{checked}</bdi>.</p>
<div class="table-wrap"><table>
<thead><tr><th scope="col">שדה</th>{headings}</tr></thead>
<tbody>{rows}</tbody>
</table></div>
<h2>אזהרות</h2><ul>{warnings}</ul>
<h2>דגלי אישור</h2>
<ul><li>נעילת טקסט: false</li><li>בדיקת נוסח הושלמה: false</li>
<li>סקירת זכויות הושלמה: false</li><li>אישור תורני: false</li>
<li>אישור פרסום: false</li></ul>
<p>קובץ זה עצמאי ואינו טוען שהמשנה, ההקלטה או הסרט אושרו.</p>
</body></html>
""".format(
        status=html.escape(str(report.get("status", "review_required"))),
        checked=html.escape(str(report.get("checked_at_utc") or "לא זמין")),
        headings=headings,
        rows=table_rows,
        warnings=warnings,
    )


def main():
    output_dir = Path("build")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_output = output_dir / "sefaria-variant-comparison.json"
    html_output = output_dir / "sefaria-variant-comparison.html"
    report = _base_report()
    report["warnings"] = ["Network or API request failed"]
    url = BASE + "?" + urlencode(
        [("version", "hebrew|" + title) for title in TITLES]
        + [("return_format", "text_only")]
    )
    try:
        request = Request(url, headers={
            "User-Agent": "MishnahFilmStudioSourceAudit/0.1",
            "Accept": "application/json",
        })
        with urlopen(request, timeout=18) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("API response exceeds safe size")
        report = compare(json.loads(data.decode("utf-8")))
    except Exception as exc:
        report["warnings"] = ["API probe failure type: " + type(exc).__name__]
        report["editions"] = [_empty_edition(title) for title in TITLES]

    json_output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    html_output.write_text(render_html(report), encoding="utf-8")
    print("SOURCE AUDIT: " + report["status"])
    for edition in report.get("editions", []):
        print(
            "EDITION: " + str(edition.get("title"))
            + " | rights=" + str(edition.get("license_declared_by_sefaria"))
            + " | words=" + str(edition.get("word_count"))
            + " | response=" + str(edition.get("sons_response_token"))
            + " (" + str(edition.get("sons_response_meaning")) + ")"
            + " | complete=" + str(all(edition.get("coverage", {}).values()))
        )
    for warning in report.get("warnings", []):
        print("WARNING: " + warning)
    print("REPORTS: " + str(html_output) + " and " + str(json_output))
    print("RELEASE: not authorized; human text and Torah review still required")
    return 0 if audit_ok(report) else 2


if __name__ == "__main__":
    sys.exit(main())
