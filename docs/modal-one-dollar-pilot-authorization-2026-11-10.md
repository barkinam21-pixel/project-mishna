# Modal OPN02 pilot — owner authorization, 2026-11-10

Owner explicitly authorized a **maximum of USD $1 total new external spend** for the Mishnah project and stated that no payment card is connected to Modal. This supersedes the previous **USD $0** spend authorization *only for a future, narrowly scoped, single OPN02 trial*; it is not permission for repeated trials, ongoing GPU deployment, spending above $1, publication, or uploading private references to unverified storage.

**Important distinction:** no card connected, a reported $1 balance, and a public price estimate are not a provider-enforced $1 budget. We have **not** verified the account's Workspace budget, credits left, private runtime, or rights to send the reference media. The production manifest's authorization flags remain false until those gates are evidenced.

## Implemented offline protection

- `tools/modal_one_dollar_policy.py` reads the existing `tools/modal_flux2_worker.py` directly and checks L4 only, max 600-second execution, max 15-second idle tail, 1 container, 0 retries, and no second undeclared Modal function.
- Uses published list prices at the time of research: L4 USD 0.000222/s; CPU USD 0.0000131/core/s; memory USD 0.00000222/GiB/s (https://modal.com/pricing). Adds **assumptions** of 4 CPU cores and 32 GiB RAM, plus USD 0.35 provision/build reserve and USD 0.20 contingency; the sum is only a *planning estimate*, not a guaranteed maximum bill.
- Always outputs `gpu_execution_authorized=false`; requires independent evidence of Workspace-level hard budget and privacy/licensing conditions before any real deployment or image request. Does not change the existing approved cache or scene/voice/release decisions.
- Local tests: 11 standard-library policy tests passed on synthetic workers (not a Modal service or full studio test). GitHub CI should verify the real worker matches these assumptions.
- The owner should **not be asked to repeat Modal credential checks**: the existing GitHub Actions run 42804205526 already verified credential presence and read-only billing access.

## Next useful engineering step

Have the existing workflow provide a safe read-only cost readiness receipt; then connect one genuinely private, authorized compute worker to the **existing** image queue, without duplicating PR #43 runtime, and generate at most one new OPN02 candidate only when actual provider limits and other gates are verified. No image has been generated under this new $1 authorization.
