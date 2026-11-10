"""Offline admission estimate for Bar's one-dollar Modal trial.

Pure, read-only calculator. NOT a provider spend cap, authorization to upload
reference images, permission to deploy, or proof of available credits.
Independent evidence of Modal's Workspace budget is mandatory.
"""
from __future__ import annotations

import argparse
import ast
from decimal import Decimal
import json
from pathlib import Path

OWNER_LIMIT = Decimal('1.00')
# Modal published list pricing, checked 2026-11-10, USD per second.
# These are not account-specific charges or a guaranteed upper bound.
PRICE_GPU_L4 = Decimal('0.000222')
PRICE_CPU_CORE = Decimal('0.0000131')
PRICE_RAM_GIB = Decimal('0.00000222')
ASSUMED_CPU_CORES = 4
ASSUMED_RAM_GIB = 32
NON_GPU_AND_BUILD_RESERVE = Decimal('0.35')
CONTINGENCY = Decimal('0.20')


def _value(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def worker_limits(path: Path):
    """Inspect the *actual* Modal worker decorator; never rely on a copied config."""
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    matches = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'generate']
    if len(matches) != 1:
        raise ValueError('EXACTLY_ONE_GENERATE_FUNCTION_REQUIRED')
    calls = [d for d in matches[0].decorator_list if isinstance(d, ast.Call) and
             isinstance(d.func, ast.Attribute) and d.func.attr == 'function' and
             isinstance(d.func.value, ast.Name) and d.func.value.id == 'app']
    if len(calls) != 1 or calls[0].args or any(k.arg is None for k in calls[0].keywords):
        raise ValueError('MODAL_FUNCTION_CONFIGURATION_UNVERIFIED')
    fields = {k.arg: _value(k.value) for k in calls[0].keywords}
    expected = {'gpu': 'L4', 'retries': 0, 'min_containers': 0, 'max_containers': 1}
    for key, value in expected.items():
        if type(fields.get(key)) is not type(value) or fields.get(key) != value:
            raise ValueError('MODAL_WORKER_UNSAFE_' + key.upper())
    t, scale = fields.get('timeout'), fields.get('scaledown_window')
    if type(t) is not int or not 1 <= t <= 600:
        raise ValueError('MODAL_WORKER_TIMEOUT_UNBOUNDED')
    if type(scale) is not int or not 0 <= scale <= 15:
        raise ValueError('MODAL_WORKER_SCALEDOWN_UNBOUNDED')
    if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
           node.name != 'generate' and
           any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and
               d.func.attr in ('function', 'cls', 'server') for d in node.decorator_list)
           for node in tree.body):
        raise ValueError('UNREVIEWED_ADDITIONAL_MODAL_FUNCTION')
    return {'gpu': 'L4', 'timeout_seconds': t, 'scaledown_seconds': scale,
            'max_containers': 1, 'retries': 0}


def assess(worker_path: Path, *, verified_workspace_budget_usd=None,
           independent_budget_evidence=False, license_cleared=False,
           references_authorized=False, private_runtime_verified=False):
    """An optimistic estimate NEVER replaces a provider-enforced spend cap."""
    base = {'owner_limit_usd': str(OWNER_LIMIT), 'provider_requests': 0,
            'new_external_spend_initiated_usd': '0',
            'workspace_usage': 'unknown', 'provider_workspace_budget_verified': False,
            'gpu_execution_authorized': False, 'status': 'BLOCKED'}
    try:
        limits = worker_limits(Path(worker_path))
    except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
        return {**base, 'reason': 'WORKER_CONTRACT_INVALID',
                'detail': str(exc).split(':', 1)[0]}
    total_seconds = limits['timeout_seconds'] + limits['scaledown_seconds']
    gpu_estimate = PRICE_GPU_L4 * total_seconds
    compute_estimate = total_seconds * (PRICE_GPU_L4 +
                    ASSUMED_CPU_CORES * PRICE_CPU_CORE +
                    ASSUMED_RAM_GIB * PRICE_RAM_GIB)
    total_estimate = compute_estimate + NON_GPU_AND_BUILD_RESERVE + CONTINGENCY
    info = {**base, 'worker': limits,
            'single_function_gpu_estimate_usd': str(gpu_estimate.quantize(Decimal('.0001'))),
            'planning_estimate_usd': str(total_estimate.quantize(Decimal('.0001'))),
            'estimate_is_a_spend_cap': False,
            'estimated_from_public_rates_not_measured_account': True}
    if total_estimate >= OWNER_LIMIT:
        return {**info, 'reason': 'ESTIMATE_REACHES_OWNER_LIMIT'}
    if not independent_budget_evidence:
        return {**info, 'reason': 'PROVIDER_WORKSPACE_BUDGET_NOT_INDEPENDENTLY_VERIFIED'}
    try:
        cap = Decimal(str(verified_workspace_budget_usd))
    except Exception:
        return {**info, 'reason': 'WORKSPACE_BUDGET_INVALID'}
    if not cap.is_finite() or cap < 0 or cap > OWNER_LIMIT:
        return {**info, 'reason': 'WORKSPACE_BUDGET_EXCEEDS_OWNER_LIMIT'}
    info['provider_workspace_budget_verified'] = True
    if not license_cleared or not references_authorized or not private_runtime_verified:
        return {**info, 'reason': 'RIGHTS_REFERENCE_OR_RUNTIME_GATE_MISSING'}
    return {**info, 'reason': 'MANUAL_SINGLE_RUN_AUTHORIZATION_AND_REMAINDER_REQUIRED'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', default='tools/modal_flux2_worker.py')
    args = parser.parse_args(argv)
    report = assess(Path(args.worker))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
