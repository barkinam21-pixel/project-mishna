"""Fail-closed GPU trial budget gate for Modal. Offline only; never calls Modal.

No automatic GPU invocation or image generation is authorized by this module.
"""
import argparse
from decimal import Decimal, InvalidOperation
import json


def check_trial(*, hourly_usd, max_seconds, available_credit_usd, hard_cap_usd,
                owner_approved=False, model_license_verified=False,
                private_runtime_verified=False):
    if not (owner_approved and model_license_verified and private_runtime_verified):
        return {"status": "BLOCKED_APPROVAL_OR_RIGHTS", "gpu_requests": 0}
    try:
        rate = Decimal(str(hourly_usd))
        seconds = Decimal(str(max_seconds))
        credit = Decimal(str(available_credit_usd))
        cap = Decimal(str(hard_cap_usd))
    except InvalidOperation:
        return {"status": "BLOCKED_INVALID_BUDGET", "gpu_requests": 0}
    if not all(v.is_finite() for v in (rate, seconds, credit, cap)):
        return {"status": "BLOCKED_INVALID_BUDGET", "gpu_requests": 0}
    if rate <= 0 or seconds <= 0 or credit <= 0 or cap <= 0:
        return {"status": "BLOCKED_INVALID_BUDGET", "gpu_requests": 0}
    estimated = rate * seconds / Decimal(3600)
    # Reserve 25% for startup, storage, rounding, and delayed billing.
    if estimated * Decimal("1.25") > min(credit, cap):
        return {"status": "BLOCKED_ESTIMATE_EXCEEDS_CAP", "gpu_requests": 0,
                "estimated_gpu_usd": str(estimated)}
    return {"status": "ESTIMATE_WITHIN_CAP_NOT_AUTHORIZED_TO_RUN",
            "gpu_requests": 0, "estimated_gpu_usd": str(estimated),
            "note": "Separate runtime hard-stop and explicit approval required."}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hourly-usd", required=True)
    p.add_argument("--max-seconds", required=True)
    p.add_argument("--available-credit-usd", required=True)
    p.add_argument("--hard-cap-usd", required=True)
    # Deliberately no flags to override owner, privacy, or license gates.
    args = p.parse_args()
    result = check_trial(hourly_usd=args.hourly_usd, max_seconds=args.max_seconds,
                         available_credit_usd=args.available_credit_usd,
                         hard_cap_usd=args.hard_cap_usd)
    print(json.dumps(result))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
