#!/usr/bin/env python3
"""Private human-review gate for the first paid OPN01 illustration.

This is NOT an image-generating tool and does not approve public release.
Review JSON must live outside the public GitHub repository.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


class VisualGateError(ValueError):
    pass


REQUIRED_CHECKS = (
    'anatomy_and_limb_count',
    'historical_footwear',
    'no_watermark_or_pseudotext',
    'shot_direction_and_continuity',
    'visual_quality_and_framing',
)


def verify_visual_gate(review_path, image_sha256):
    """Require image-specific human acceptance before even a private film preview."""
    if review_path is None:
        raise VisualGateError('No visual approval: generated artwork is unreviewed or rejected')
    path = Path(review_path)
    if path.is_symlink() or not path.is_file() or not (10 <= path.stat().st_size <= 4096):
        raise VisualGateError('Missing or invalid private visual approval file')
    if not re.fullmatch(r'[0-9a-f]{64}', str(image_sha256)):
        raise VisualGateError('Invalid image identity')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise VisualGateError('Unreadable visual approval') from exc
    if not isinstance(data, dict):
        raise VisualGateError('Visual approval must be a JSON object')
    if data.get('shot') != 'OPN01' or data.get('image_sha256') != image_sha256:
        raise VisualGateError('Visual approval is not for this image and shot')
    if data.get('decision') != 'ACCEPT_FOR_PRIVATE_PREVIEW':
        raise VisualGateError('Illustration is rejected or review is incomplete')
    if data.get('reviewer_type') != 'human' or not isinstance(data.get('reviewer_name'), str) or not data['reviewer_name'].strip():
        raise VisualGateError('Missing identifiable human review')
    checks = data.get('checks')
    if not isinstance(checks, dict) or any(checks.get(k) is not True for k in REQUIRED_CHECKS):
        raise VisualGateError('One or more required visual checks are not explicitly passed')
    if data.get('public_release_authorized') is not False:
        raise VisualGateError('Visual acceptance cannot confer public-release permission')
    try:
        reviewed = datetime.fromisoformat(data['reviewed_at_utc'].replace('Z', '+00:00'))
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise VisualGateError('Invalid review time') from exc
    if reviewed.tzinfo is None or reviewed > datetime.now(timezone.utc):
        raise VisualGateError('Visual review timestamp must be past and timezone-aware')
    return {'status': 'VISUAL_ACCEPTED_FOR_PRIVATE_PREVIEW_ONLY', 'shot': 'OPN01',
            'public_release_allowed': False, 'approved_image_sha256': image_sha256}
