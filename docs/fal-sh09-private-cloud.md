# SH09 private-reference cloud pilot

Status: prepared but **not activated**. The original reference image is private and must **never** be committed to this public repository, copied into a PR, or embedded in a workflow log.

## Security boundary
- `FAL_KEY` is stored as a GitHub Actions repository secret.
- `FAL_SH09_REFERENCE_URL` is a **separate** GitHub Actions repository secret, intended for a short-lived HTTPS signed download URL from a private object-storage provider. This is not yet configured.
- The workflow fails before any fal.ai call if either secret is absent. It never prints either secret or the image.
- No redirects are followed; downloaded reference must be PNG and <=12 MB. The runner is ephemeral.
- The reference image is transmitted to fal.ai only after explicit paid-run confirmation. The output is retained as a private GitHub Actions artifact for seven days. Review artifact access permissions.
- A signed URL is a bearer credential; use the shortest practical expiration and private storage. Never place it in chat, issue comments, or source control.

## Operator sequence (not yet authorized)
1. Place the chosen reference PNG in private storage, generate a short-lived HTTPS signed URL, and set `FAL_SH09_REFERENCE_URL` as a GitHub Actions secret. This requires a real private storage integration; **not accomplished** by attaching an image to ChatGPT.
2. Confirm fal.ai credits, disable auto-recharge, and verify provider-side spend controls. The `--max-budget-usd 10` argument is **not** a hard fal.ai billing limit.
3. On GitHub Actions, manually dispatch `fal.ai SH09 manual one-image pilot` and enter exact `YES` only after a separate approval for one paid image.
4. Inspect the private candidate artifact and actual fal.ai usage; do not auto-approve or rerun.

No schedule, cron, or automatic paid dispatch is installed. This workflow is one-image only, not an end-to-end cinematic video pipeline.
