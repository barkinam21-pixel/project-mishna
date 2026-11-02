# Copilot Pro image generation — verified research, 2026-11-01

**RESEARCHED, NOT EXECUTED.** Bar confirms paying $10/month for GitHub Copilot Pro. No new purchase or SDXL prompt-only rerun authorized.

## Official facts

- GitHub launched image generation/editing in Copilot on **2026-10-28**, public preview, using **GPT Image 2.5 Flare**. Supported surfaces: **VS Code, Copilot app, Copilot CLI**. Images preview in chat and save to the project: https://github.blog/changelog/2026-10-28-generate-and-edit-images-directly-in-copilot/ and https://docs.github.com/en/copilot/concepts/agent-capabilities/agent-powered-workflows-and-operations/image-generation
- **Copilot Pro is eligible**, but generated images **consume AI credits based on image tokens**, separately from chat reasoning. This is **NOT unlimited image generation**. Pro currently lists **1,000 base + 500 flex AI credits monthly**, flex may change. Only inline code suggestions and next-edit suggestions are unlimited, not agent or image calls: https://docs.github.com/en/copilot/get-started/plans and https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/billing
- Copilot Vision accepts user-approved PNG/JPEG reference images in VS Code and CLI, but availability of vision does **not** prove faithful image-reference conditioning by the generator: https://github.blog/changelog/2026-07-01-copilot-vision-is-generally-available/
- Colab free GPU is not guaranteed or unlimited: https://research.google.com/colaboratory/faq.html

## Actual production problem

Several real SH09 SDXL outputs failed **scene fidelity** (one man in daytime dunes; ornate modern-looking storefront with no people). Neither prompt softening, guidance nor seed changes have been verified to solve it. Reject these as production assets.

## Minimal one-image gate

1. Verify accessible Copilot app/VS Code/CLI image generation and remaining credit/spend controls; **never enable overages**. Do not claim GitHub cloud coding-agent chat itself offers the image tool.
2. With permission to use the user's reference art, request **ONE** original 16:9 illustration: exactly **two distinct adult brothers**, both approaching **one modest ancient stone courtyard-house doorway** at night; oil lamp by door, readable figures, deep blue night, soft warm painterly brushwork and slightly muted but legible colors. **No commercial windows, ornate shopfront, palace, empty scene, solo traveler or daytime dunes.** Dramatization, not historically documented event.
3. Review **actor count and action, ancient architecture and night first**, style second. Log actual credit usage and image hash; keep image private and unapproved pending user's review.
4. If wrong, stop; investigate **real reference/pose/depth/ControlNet/inpainting** instead of rerolling or producing all 16.

## Open limitations

The connected GitHub repository tool can edit code, not call the new Copilot app/CLI image-generation interface. **No image has been generated with Copilot yet.** Per-image credits, fidelity, reference conditioning, commercial rights and account balance remain unverified. GitHub Actions does not provide an unlimited generative GPU. Prefer one bounded test using the already-paid feature before any new subscription.
