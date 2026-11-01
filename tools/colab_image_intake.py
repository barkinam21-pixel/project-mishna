"""Offline intake of real Colab trial PNGs into a PRIVATE, unapproved review queue.

Default: read-only audit. --stage writes only to git-ignored private-media/.
No image generation, cloud calls, media approval, public upload, or spending.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "episodes" / "berakhot-01-01"
PACK = EPISODE / "free-cloud-image-prompts.json"
TRIALS = EPISODE / "trials.json"
EXAMPLE = EPISODE / "private-proof-assets.example.json"
STAGE = ROOT / "private-media" / "colab-intake"
PNG = re.compile(r"SH(0[1-9]|1[0-6])\.png\Z")
SUPERSEDED = re.compile(r"SH(0[1-9]|1[0-6])\.superseded-[a-f0-9]{12}\.png\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
META = {"prompt-pack-snapshot.json", "usage-ledger.jsonl"}
REVIEW_SHEET = "review-contact-sheet.jpg"  # derived JPEG preview, NEVER an original art source
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_ZIP_BYTES = 360 * 1024 * 1024


class ArchiveError(ValueError):
    """A ZIP is not a verified Colab image delivery."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify_png(data):
    """Validate full PNG chunk CRCs and actual lossless scanlines, without Pillow."""
    if len(data) < 57 or not data.startswith(PNG_SIGNATURE):
        raise ArchiveError("PNG signature or content missing")
    cursor, width, height, channels = 8, None, None, None
    idat, seen_end = [], False
    while cursor < len(data):
        if cursor + 12 > len(data):
            raise ArchiveError("truncated PNG chunk")
        length = struct.unpack(">I", data[cursor:cursor + 4])[0]
        chunk_type = data[cursor + 4:cursor + 8]
        end = cursor + 12 + length
        if length > MAX_IMAGE_BYTES or end > len(data):
            raise ArchiveError("oversized or truncated PNG chunk")
        payload = data[cursor + 8:cursor + 8 + length]
        expected_crc = struct.unpack(">I", data[cursor + 8 + length:end])[0]
        if zlib.crc32(chunk_type + payload) & 0xffffffff != expected_crc:
            raise ArchiveError("PNG chunk checksum mismatch")
        if cursor == 8:
            if chunk_type != b"IHDR" or length != 13:
                raise ArchiveError("missing PNG IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if (depth != 8 or color not in (2, 6) or compression != 0
                    or filtering != 0 or interlace != 0
                    or width not in (768, 1024) or height not in (448, 576)):
                raise ArchiveError("PNG size or pixel format outside tested Colab settings")
            channels = 3 if color == 2 else 4
        elif chunk_type == b"IDAT":
            idat.append(payload)
        elif chunk_type == b"IEND":
            if length != 0 or end != len(data):
                raise ArchiveError("trailing data after PNG end")
            seen_end = True
        cursor = end
    if not seen_end or not idat:
        raise ArchiveError("PNG missing image stream or end marker")
    scanline = 1 + width * channels
    limit = scanline * height
    try:
        stream = zlib.decompressobj()
        raw = stream.decompress(b"".join(idat), limit + 1)
        if stream.unconsumed_tail or not stream.eof or stream.unused_data:
            raise ArchiveError("PNG decompression exceeds expected pixels or stream not complete")
        raw += stream.flush()
    except zlib.error as exc:
        raise ArchiveError("PNG image stream cannot be decoded") from exc
    if len(raw) != limit or not stream.eof or stream.unused_data:
        raise ArchiveError("PNG scanlines are truncated or malformed")
    if any(raw[row * scanline] > 4 for row in range(height)):
        raise ArchiveError("invalid PNG row filter")
    return [width, height]


def archive_members(zf):
    infos = zf.infolist()
    if len(infos) > 100 or sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
        raise ArchiveError("ZIP exceeds safe image batch limits")
    seen = set()
    for info in infos:
        name = info.filename
        if (name in seen or name.startswith("/") or "/" in name
                or "\\" in name or ".." in name
                or name not in META and name != REVIEW_SHEET
                and not PNG.fullmatch(name) and not SUPERSEDED.fullmatch(name)):
            raise ArchiveError("unexpected, duplicate, or unsafe ZIP entry")
        if info.is_dir() or (info.external_attr >> 16 & 0o170000) == 0o120000:
            raise ArchiveError("directory/symlink entries are not accepted")
        if info.file_size > MAX_IMAGE_BYTES and name.endswith(".png"):
            raise ArchiveError("PNG exceeds 20 MiB")
        if name in META and info.file_size > 2 * 1024 * 1024:
            raise ArchiveError("metadata exceeds 2 MiB")
        if name == REVIEW_SHEET and info.file_size > 12 * 1024 * 1024:
            raise ArchiveError("review JPEG exceeds 12 MiB")
        seen.add(name)
    if not META.issubset(seen):
        raise ArchiveError("missing Colab snapshot or usage ledger")
    return sorted(name for name in seen if PNG.fullmatch(name))


def audit_archive(archive, pack_path=PACK, trials_path=TRIALS):
    """Return verified draft-image descriptors; never grant usage/rights approval."""
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    rejected = {trial.get("image_sha256") for trial in
                json.loads(Path(trials_path).read_text(encoding="utf-8")).get("trials", [])
                if trial.get("production_asset_accepted") is not True}
    known = {shot["shot_id"]: shot for shot in pack["shots"]}
    archive_path = Path(archive)
    if archive_path.stat().st_size > MAX_ZIP_BYTES:
        raise ArchiveError("ZIP compressed size exceeds safe batch limit")
    digest_state = hashlib.sha256()
    with archive_path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest_state.update(block)
    archive_sha = digest_state.hexdigest()
    candidates, skipped, seen_hash = [], [], set()
    with zipfile.ZipFile(archive) as zf:
        image_names = archive_members(zf)
        snapshot = json.loads(zf.read("prompt-pack-snapshot.json").decode("utf-8"))
        ledger_lines = zf.read("usage-ledger.jsonl").decode("utf-8").splitlines()
        ledger = [json.loads(line) for line in ledger_lines if line.strip()]
        has_review_sheet = REVIEW_SHEET in zf.namelist()
        if has_review_sheet:
            preview_bytes = zf.read(REVIEW_SHEET)
            if not (len(preview_bytes) > 4 and preview_bytes.startswith(b"\xff\xd8")
                    and preview_bytes.endswith(b"\xff\xd9")):
                raise ArchiveError("invalid derived review JPEG")
        if (snapshot.get("episode_id") != "berakhot-01-01"
                or snapshot.get("status") != "private_style_tests_only"
                or snapshot.get("source_lock") is not False
                or snapshot.get("torah_review_approved") is not False
                or snapshot.get("visual_direction_approved") is not False
                or snapshot.get("public_release_authorized") is not False
                or snapshot.get("monetary_spend_authorized_usd") != 0
                or snapshot.get("model_id") != pack["model_id"]):
            raise ArchiveError("snapshot does not preserve draft-only and no-spend gates")
        for name in image_names:
            shot_id = name[:-4]
            image = zf.read(name)
            actual = sha256(image)
            if shot_id == "SH01" or actual in rejected:
                skipped.append({"shot_id": shot_id, "reason": "rejected_SH01_or_trial_hash"})
                continue
            shot = known.get(shot_id)
            old_shot = next((s for s in snapshot.get("shots", [])
                             if isinstance(s, dict) and s.get("shot_id") == shot_id), None)
            if not shot or not old_shot:
                raise ArchiveError("unknown shot in Colab ZIP: " + shot_id)
            if (old_shot.get("shot_prompt") != shot["shot_prompt"]
                    or snapshot.get("style_lock") != pack["style_lock"]
                    or snapshot.get("negative_prompt") != pack["negative_prompt"]
                    or old_shot.get("seed") != shot["seed"]):
                raise ArchiveError(shot_id + ": stale prompt, scene design, or seed")
            size = verify_png(image)
            evidence = [entry for entry in ledger if isinstance(entry, dict)
                        and entry.get("shot_id") == shot_id
                        and entry.get("image_sha256") == actual]
            if not evidence:
                raise ArchiveError(shot_id + ": missing matching image SHA in Colab ledger")
            record = evidence[-1]
            spec = record.get("generation_spec")
            if not isinstance(spec, dict):
                raise ArchiveError(shot_id + ": missing reproducible generation specification")
            full_prompt = pack["style_lock"] + ". Shot direction: " + shot["shot_prompt"]
            expected_prompt = sha256(full_prompt.encode("utf-8"))
            spec_sha = sha256(json.dumps(spec, sort_keys=True).encode("utf-8"))
            if (not SHA256.fullmatch(str(record.get("generation_spec_sha256", "")))
                    or record.get("generation_spec_sha256") != spec_sha
                    or record.get("prompt_sha256") != expected_prompt
                    or spec.get("prompt_sha256") != expected_prompt
                    or spec.get("negative_prompt_sha256") != sha256(pack["negative_prompt"].encode("utf-8"))
                    or spec.get("seed") != shot["seed"]
                    or spec.get("model_id") != pack["model_id"]
                    or record.get("model_id") != pack["model_id"]
                    or record.get("model_license") != pack["model_license"]
                    or spec.get("variant") != "fp16"
                    or spec.get("guidance_scale") != 6.0
                    or spec.get("inference_steps") != record.get("inference_steps")
                    or [spec.get("width"), spec.get("height")] != size
                    or record.get("image_size") != size
                    or record.get("operation") != "image_generate"
                    or record.get("accepted") is not False
                    or record.get("public_release_authorized") is not False
                    or record.get("paid_api_calls") != 0
                    or record.get("external_cash_spend_initiated_usd") != 0
                    or spec.get("model_revision") != "unknown"):
                raise ArchiveError(shot_id + ": inconsistent generation, hash, or no-spend evidence")
            if actual in seen_hash:
                raise ArchiveError("duplicate image bytes for different shots")
            seen_hash.add(actual)
            candidates.append({
                "shot_id": shot_id,
                "sha256": actual,
                "image_size": size,
                "model_id": record.get("model_id"),
                "model_revision": "unknown",
                "model_license_reported": record.get("model_license", ""),
                "generation_spec_sha256": spec_sha,
                "provenance": "Colab ZIP sha256:" + archive_sha,
                "status": "draft_needs_visual_rights_source_review",
            })
    return {
        "status": "DRAFT_IMAGES_FOUND" if candidates else "NO_NEW_ELIGIBLE_IMAGES",
        "episode_id": "berakhot-01-01",
        "archive_sha256": archive_sha,
        "draft_images": candidates,
        "skipped": skipped,
        "image_count": len(candidates),
        "review_contact_sheet_present": has_review_sheet,
        "external_spend_authorized_usd": 0,
        "workspace_usage": "unknown",
        "ready_for_render": False,
        "public_release_authorized": False,
    }


def stage_archive(archive, report, output_dir=STAGE):
    """Stage verified PNGs locally without affecting the public repository or gates."""
    if report["status"] != "DRAFT_IMAGES_FOUND":
        raise ArchiveError("nothing eligible for private staging")
    output_dir = Path(output_dir)
    if output_dir.is_symlink():
        raise ArchiveError("refusing symlink stage path")
    output_dir.mkdir(parents=True, exist_ok=True)
    items = []
    with zipfile.ZipFile(archive) as zf:
        for item in report["draft_images"]:
            name = item["shot_id"] + ".png"
            image = zf.read(name)
            if sha256(image) != item["sha256"]:
                raise ArchiveError("archive changed since validation")
            filename = item["shot_id"] + "-" + item["sha256"][:16] + ".png"
            target = output_dir / filename
            if target.exists():
                if target.is_symlink() or sha256(target.read_bytes()) != item["sha256"]:
                    raise ArchiveError("unsafe or conflicting staged image")
            else:
                with target.open("xb") as dst:
                    dst.write(image)
            # Deny approval by default; this is a review candidate, not film media.
            items.append({
                "shot_id": item["shot_id"],
                "path": str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
                "sha256": item["sha256"],
                "original_illustration": False,
                "accepted_for_private_preview": False,
                "rights_verified_for_private_preview": False,
                "license": item["model_license_reported"],
                "provenance": item["provenance"],
                "generation_spec_sha256": item["generation_spec_sha256"],
            })
    preview_rel = None
    if report.get("review_contact_sheet_present"):
        with zipfile.ZipFile(archive) as zf:
            preview_data = zf.read(REVIEW_SHEET)
        preview_file = output_dir / ("review-sheet-" + report["archive_sha256"][:16] + ".jpg")
        if preview_file.exists():
            if preview_file.is_symlink() or preview_file.read_bytes() != preview_data:
                raise ArchiveError("unsafe or conflicting preview sheet")
        else:
            with preview_file.open("xb") as dst:
                dst.write(preview_data)
        preview_rel = (str(preview_file.relative_to(ROOT)) if preview_file.is_relative_to(ROOT)
                       else str(preview_file))
    config = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    config["status"] = "staged_for_visual_review_only"
    if preview_rel:
        config["review_contact_sheet"] = preview_rel
    config["images"] = items
    config["notes"].append("Offline ZIP verified, not visually reviewed; all private/rights/Torah approvals remain false.")
    config["notes"].append("Model weights revision is unknown; inspect provenance and applicable licenses before acceptance.")
    output = output_dir / ("review-candidate-" + report["archive_sha256"][:16] + ".json")
    content = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    if output.exists():
        if output.is_symlink() or output.read_text(encoding="utf-8") != content:
            raise ArchiveError("conflicting review candidate report")
    else:
        with output.open("x", encoding="utf-8") as dest:
            dest.write(content)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="real Colab trial ZIP, never a test-only media substitute")
    parser.add_argument("--stage", action="store_true", help="copy verified PNGs into git-ignored private-media; no approvals")
    args = parser.parse_args(argv)
    try:
        report = audit_archive(args.archive)
        if args.stage and report["status"] == "DRAFT_IMAGES_FOUND":
            report["review_candidate_path"] = str(stage_archive(args.archive, report))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    except (ArchiveError, ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "INVALID", "reason": str(exc), "ready_for_render": False},
                         ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
