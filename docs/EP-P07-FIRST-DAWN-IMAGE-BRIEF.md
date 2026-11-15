# EP-P07 — shot-specific dawn image production brief (DRAFT, no inference)

**Purpose:** turn already demonstrated Cloudflare single-image generation into one consistent *original* illustration ready for the 15-shot prologue, instead of repeatedly retesting Free/Drive/model access.

**Existing source of truth:** `episodes/berakhot-01-01/scene-prologue-v02.json` shot `EP-P07`, first-scene dawn bible, `docs/epic-intro-prologue-shotmap-v02.md#P07`, private visual canon referenced in `AGENTS.md` and `docs/PROJECT-VERIFIED-FACTS.json`. This is a symbolic dramatization, **not** identification of known historical travelers. Current shot source record has `verified=false`, so do not label it researched/approved.

## Locked scene facts

- Placement: `EP-P07`, frames **840–1008** at 24 fps: **7.0 seconds**. Previous `EP-P06` details, next `EP-P08` younger traveler slows.
- **Original, wide master from behind**, not a crop or legacy OPN02. Two traveling figures share the winding path toward a small stone hilltop village beyond low Judean-style rocky hills and scattered olive trees.
- **Elder screen-left**, aged gray-white beard and pale wrapped head covering, heavy but natural dark-blue cloak, satchel. **Younger screen-right**, darker beard/hair, earth-brown outer wrap over pale linen tunic, satchel. Both walk away from camera. In a wide shot faces should not become oversized portraits.
- **Dawn, not sunset**. Before-sunrise cool-blue environmental shadows with restrained warm rim from **screen-left**. Do not copy sunset orange skies, sunset lamps or the previously rejected Cloudflare images.
- Fixed 180-degree line: camera on **south side of travel line**; travel screen direction **right-to-left**. Correct left/right spacing and plausible silhouette, scale and gait. No unplanned line crossing.
- Cinematic oil/gouache painted realism; tactile brush grain, imperfect natural edges, believable cloth, rock and skin. Mature and inviting, no gloss/plastic photorealism, no childish cartoon, no horror. Render **16:9** and if the pinned Cloudflare preview is used retain its **1024×576** pixels.

## Actual reference roles (owner-private SHA-verified bundle)

- `REF01_CAST_HERO_PAINTED_MASTER.jpg` — primary **identity + visual texture** (not scene image to reuse).
- `REF03_TRAVEL_REAR_WIDE.jpg` — primary **rear-wide framing + relative scale**.
- `REF04_JOURNEY_WIDE_ORIGINAL.jpg` — primary **geography, road and hilltop stone village**.
- Other dialogue alternates (`REF05–07`) are not primary for this wide master; `REF02` is a collage/moodboard only, not model shot-conditioning; private MP4s, old `OPN02`/`OPN03` sunset candidates are excluded.

## Original image direction (draft prompt, not a billable request)

> Cinematic mature painterly oil-and-gouache illustration, 16:9 wide rear master of two anonymous travelers on a winding rocky path in an ancient Judean-style hill landscape, early predawn blue ambient light and delicate warm first light entering from screen left. Older traveler on screen left, modest blue cloak, pale wrapped head covering, gray-white beard suggested in side silhouette, weathered satchel; younger on screen right, brown outer wrap over pale tunic, darker hair and beard, small satchel. People are believable human scale and subordinate to landscape, walking away toward a modest stone hilltop village, sparse olive trees and dry grass, cohesive physical space, restrained expressive body language, grounded shadow, rich but subtle hand-painted brush texture, serious poetic historical dramatization, clear cinematic geography and deep focal separation; fresh original composition, NOT a redraw/crop of a reference.

**Negative constraints:** evening/sunset sky, bright orange twilight or glowing village lamps, giant heroic figures, fortress/castle village, photorealistic plastic skin, Disney-ish/chibi exaggeration, extra characters, duplicate hands, costume color swaps, camera axis crossing, unreadable pseudo-lettering, invented Hebrew script, signs, text, logos, watermarks or synthetic graphic overlays.

**Continuity acceptance checklist:** the two identities do not drift versus REF01, elder remains left and younger right, both proportions and bags are consistent, early dawn lighting from screen left is physically plausible, settlement reads as **village** not fortress, image is a distinct original, poses and path connect naturally with P06 and P08. Reject image with face/hand/cloth errors instead of calling it accepted. Avoid trying again automatically after a provider error or uncertain POST.

## Gate and next implementation

This brief is **production direction, not approval**. No new image model call is made by saving it. Private assets have been recovered and validated. Cloudflare **historically worked** and the owner confirmed Workers Free; **do not ask again for those screenshots**. Fresh request-specific budget/quota, model-reference rights, source review, successful hosted reservation, and explicit new one-shot approval cannot be replaced with the historic consumed OPN03 ticket. Keep `generation-safety.json` CLOSED until a separately approved scoped attempt, and do not claim any image was generated here.