# fal.ai SH09 pilot — no purchase authorized

This is an **optional**, one-image, image-reference proof for Mishnah Cinema. It replaces the Colab GPU runtime with fal.ai's hosted FLUX.2 Pro **edit** endpoint, `fal-ai/flux-2-pro/edit`. The source reference stays out of GitHub; in a paid run it is transmitted to fal.ai as a base64 image input. Only submit images you have the right to use.

**Current state:** implementation prepared; no real paid API request, no verified image, no purchase.

## Safe default (zero spend)

```sh
python tools/fal_sh09.py --reference /private/path/brothers.png
```

This prints a plan only; it makes **no network calls** and uploads nothing. It needs only Python's standard library. Keep the reference outside the public repository.

## Later, only after explicit approval and API key setup

```sh
export FAL_KEY="your-private-key"
python tools/fal_sh09.py --reference /private/path/brothers.png --authorize-paid --max-budget-usd 50
```

Do **not** paste a key into ChatGPT, an issue, a PR, a screenshot or public GitHub code. On GitHub Actions, use a repository secret and a manual workflow with a trusted private reference delivery method; none is installed here yet. No scheduled job should call the paid command.

## Safeguards and limitations

- Only a single image is submitted, with no retry. A local ledger is reserved **before** the request and prevents a second run in the same output directory. Failures remain marked as uncertain because fal.ai might have billed even if the client timed out.
- A **$0.25 internal reservation** is used for this pilot; it is a conservative bookkeeping allowance, **not** fal.ai's price quote, actual usage, or an enforced provider-wide cap.
- The `--max-budget-usd` flag accepts at most $50, but **does not cap billing on fal.ai's servers or across devices/runs**. Configure fal.ai billing/spending controls separately and inspect actual charges. Do not enable automatic recharge without separate approval.
- The output, if received, is `local-output/fal-sh09/SH09_fal_unreviewed.png`. It is **not** marked approved and must pass human visual QA.
- The program has not been GPU/API-tested. Check the live endpoint schema and pricing again immediately before first paid request.
- Run `python -m unittest discover -s tests -p 'test_fal_sh09.py'` for offline checks.

Official docs: https://fal.ai/models/fal-ai/flux-2-pro/edit/api and https://fal.ai/pricing .
