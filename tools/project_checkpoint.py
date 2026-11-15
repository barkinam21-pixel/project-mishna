"""Report persistent verified facts separately from per-attempt generation gates.

No network, no credentials, no inference. A closed one-shot gate must never
make a prior successful Cloudflare image/Free confirmation appear 'lost'.
"""
import argparse
import json
from pathlib import Path

CHECKPOINT = 'docs/PROJECT-VERIFIED-FACTS.json'
GATE = 'episodes/berakhot-01-01/generation-safety.json'
EXPECTED = {
    'cloudflare_free_owner_confirmed',
    'cloudflare_model_successful_before',
    'private_reference_archive_preserved',
    'private_scene_reference_code_prepared',
    'prior_privacy_review_and_waiver_documented',
}


class CheckpointError(ValueError):
    pass


def summarize(data, gate):
    """Pure status, never a grant of rights, budget or provider access."""
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise CheckpointError('CHECKPOINT_FORMAT_INVALID')
    facts = data.get('verified_reusable_facts')
    if not isinstance(facts, list) or len(facts) != len(EXPECTED):
        raise CheckpointError('CHECKPOINT_FACT_COUNT_CHANGED')
    keys = [f.get('key') for f in facts if isinstance(f, dict)]
    if len(keys) != len(EXPECTED) or set(keys) != EXPECTED or len(set(keys)) != len(keys):
        raise CheckpointError('CHECKPOINT_FACT_SET_CHANGED')
    for f in facts:
        if (f.get('value') is not True or
            not isinstance(f.get('evidence'), str) or not f['evidence'].strip() or
            not isinstance(f.get('scope'), str) or not f['scope'].strip()):
            raise CheckpointError('CHECKPOINT_EVIDENCE_MISSING')
    policy = data.get('current_permission')
    retry = data.get('retry_policy')
    focus = data.get('active_focus')
    if (not isinstance(policy, dict) or policy.get('reopen_from_historical_evidence_only') is not False
        or policy.get('never_reuse_consumed_ticket') is not True
        or not isinstance(retry, dict)
        or not isinstance(retry.get('never_ask_owner_to_repeat'), list)
        or len(retry['never_ask_owner_to_repeat']) < 3
        or not isinstance(retry.get('fresh_check_only_when_needed_for_new_external_request'), list)
        or not isinstance(focus, dict) or focus.get('shot_id') != 'EP-P07'
        or focus.get('cost_and_generation_this_checkpoint') != 0):
        raise CheckpointError('CHECKPOINT_POLICY_OR_FOCUS_CHANGED')
    if not isinstance(gate, dict) or any(type(gate.get(k)) is not bool
                                      for k in ('privacy_verified', 'free_hard_cap_verified', 'quota_verified')):
        raise CheckpointError('GENERATION_GATE_INVALID')
    open_now = all(gate[k] is True for k in ('privacy_verified', 'free_hard_cap_verified', 'quota_verified'))
    return {
        'status': 'CHECKPOINT_REUSED_NO_NEW_PROVIDER_CALL',
        'reusable_verified_facts': keys,
        'reask_owner_for_historical_facts': False,
        'first_original_dawn_shot': focus['shot_id'],
        'next_safe_operation': focus['next_safe_operation'],
        'last_consumed_generation_gate_open': open_now,
        'note': ('This only mirrors gate flags; new image requests additionally require'
                 ' fresh scoped authorization, accounting, editorial and rights review.'),
        'image_requests': 0,
        'new_images_generated': 0,
        'external_cost_usd': 0,
        'provider_dispatch_authorized': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    try:
        data = json.loads((root/CHECKPOINT).read_text(encoding='utf-8'))
        gate = json.loads((root/GATE).read_text(encoding='utf-8'))
        print(json.dumps(summarize(data, gate), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        msg = str(exc) if isinstance(exc, CheckpointError) else type(exc).__name__
        print(json.dumps({'status': 'BLOCKED', 'reason': msg, 'image_requests': 0,
                          'provider_dispatch_authorized': False}, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())