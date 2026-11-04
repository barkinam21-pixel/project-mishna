# Main narrator: audition direction, not approved casting

Bar requests an Israeli Hebrew narrator perceived around 55–65: warm, wise, kind, patient, moderately deep, quietly lively and clear. Avoid frailty, rasp, fatigue, exaggerated old age or monotony. The narrator is a separate contemporary guiding voice, not a named Tanna or an impersonation of a historical sage. Elder character voices remain separately cast; no character voice is approved by this experiment.

The working Avri sample remains preserved and the default is unchanged. An optional comparison uses the same original generic audition text for both takes, avoiding unapproved Mishnah variants or historical claims. Baseline: Avri, rate -3%, default pitch. Candidate: same Avri, rate -6%, pitch -3%, default volume. These are experimental engineering choices, not a guarantee of age, warmth or human identity. No pitch-shifting postprocessing, cloning, unsupported expressive style or paid voice service.

Azure SSML supports rate and pitch, but support and perceived effect must be confirmed in the actual voice output: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice . No claim that Avri has a dedicated elderly/warm style.

The existing main-only, owner-dispatched, F0-verified and encrypted workflow gains compare_narrator=false by default. With synthesize=true and compare_narrator=true it issues exactly two short requests, with no retries. Both WAV files must decode correctly before the ciphertext is uploaded. Failure on either stops the comparison. No permanent narrator default changes. F0 remaining quota is unknown; a quota error must stop rather than change pricing.

Human review compares intelligibility, pronunciation, friendliness, energy, age impression, pitch continuity and distinction from elder characters. The reference sample is https://drive.google.com/file/d/1zUWMsuuiyN7oupgRzT7HkSF6p4cdSamV/view . Approval of the connection is not approval of the voice performance.


## Superseding casting decision — 2026-11-04

Owner explicitly REJECTED Avri for the series narrator and as the desired vocal model. Do not produce further Avri casting takes. Legacy settings and earlier samples are technical backups only, not approved casting. No narrator is currently selected. Owner wants a unique, stable, warm wise male guiding voice perceived 55–65, natural Israeli Hebrew with no foreign accent; elderly scene characters remain separate.

Official Azure docs list AndrewMultilingualNeural and BrianMultilingualNeural with Hebrew support: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice . Both are different preset identities, NOT newly created custom voices and NOT guaranteed Israeli accents or age matches. The optional new_narrators path checks live Male/SecondaryLocaleList=he-IL metadata before two short same-text requests and fails closed if either is absent. Same -3% rate, no pitch or expressive styles, explicit he-IL lang. Exact model identifiers are stored in tools/new_narrator_auditions.py. Service model version/seed are not exposed or pinned; immutable identity across future vendor updates is not guaranteed.

No paid/custom voice, account changes, clones or subscription started. No new samples generated before authorized merge of this optional workflow. Native male Hebrew in the official standard list is Avri only (Hila is female); multilingual candidates are experiments and foreign accent is a rejection criterion. Do not promise an adequate native male alternative merely because a locale is supported. Other connected tools offer paid synthesis or unknown canary billing; none invoked without cost authorization.

Short audition text is original neutral modern narration, not ancient quotation. After owner chooses a candidate, prepare the requested 60–90 second source-checked pronunciation/consistency assessment including properly attributed Mishnah, verse and names. Do not claim short samples satisfy that longer approval gate, or change original text to hide pronunciation failures. Human listening required; ASR and signal measurements are auxiliary only.


## Casting feedback and engine constraint — 2026-11-04

Owner listened: Brian closer than Andrew but NOT suitable; neither selected. Avri remains rejected. Do not offer renamed/pitch-shifted/slowed variants of these three as new personalities. No final narrator approved. Need three distinct warm mature male personalities with native-sounding Israeli Hebrew; linguistic and expressive quality requires listening, not catalog labels. No films authorized.

Connected Maudio offers a fixed-text Gemini 3.1 Flash TTS pronunciation canary with Charon, Iapetus and Sadaltager, capped globally at three successful generations. Tool schema exposes voice only: no custom text, SSML, lexicon, seed, token budget, billing preflight or free-only switch. It is a plausible next ENGINE experiment, not proven native Hebrew or an exact age match. Three options use the wrapper's fixed test text, whose exact contents cannot be inspected from the current schema before calling. No generated clip yet; do not claim every word checked. No equivalence to the Azure comparison text established.

Official Google speech-generation docs directly checked: Hebrew supported; voice descriptions include Charon informative, Iapetus clear, Sadaltager knowledgeable. Gemini uses prompt-based direction/audio tags, not Azure SSML. Stable preset ID does not guarantee stable model behavior; no exposed seed in this tool. Official pricing checked: gemini-3.1-flash-tts-preview lists a free standard tier and paid pricing of $1 per million input text tokens and $20 per million output audio tokens, 25 audio tokens per second. Account tier of the connected tool cannot be verified here; advertised free tier is NOT evidence that this connection is free. No calls submitted because owner prohibits paid service without explicit approval.

Sources: https://ai.google.dev/gemini-api/docs/speech-generation ; https://ai.google.dev/gemini-api/docs/pricing . Read-only HeyGen catalog lookup for Hebrew male Middle-aged/Old returned no items; this does not prove no voices exist in its full catalog. Current managed environment has no secret bindings or outbound identities for a directly verified Gemini free-tier project. No secret requested in chat.

Next gate: either verified free-only billing guard on the Maudio connection or explicit authorization of possible paid consumption for three fixed-text calls; neither is currently established. Do not start another Azure PR or a new cloud platform merely to bypass this gate.


## Verified no-external-charge CPU Hebrew experiment — 2026-11-04

Owner authorized free-only alternatives, not possible Gemini charges. No Maudio/Gemini synthesis was called. Ran isolated Chatterbox Multilingual V3 on existing workspace CPU (no new VM/GPU/API). MIT code/model declaration: https://huggingface.co/ResembleAI/chatterbox and upstream LICENSE. Exact HF revision 5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18; all downloaded LFS weights matched published SHA256. Package 0.1.7, CPU torch/torchaudio 2.6.0. Isolated compatibility patch: from_local loads V3 filename instead of V2, strict state_dict passed. Production Azure code/settings/secrets unchanged. Dependency fixes: PyPI torchaudio required replacement with CPU wheel; offline ASR used FFmpeg float input to avoid PyAV19 metadata_errors incompatibility.

Exactly two generation trials with seed731, cfg0, exaggeration0.3, temperature0.8, vendor built-in voice; NO Avri/Andrew/Brian reference or cloning. First unpointed 8.44s take failed rough Hebrew ASR badly. Optional dicta_onnx diacritizer was unavailable. Second take used explicitly vocalized modern generic audition text; removing niqqud equals original words exactly. Result 7.24s mono PCM16/24kHz, SHA256 263fb696fc56ff00b24f48cd69e0117a79d020c6c20bc413c47da2d6086626cd. 85.83s generation time excluding initialization. Full FFmpeg decode passed. Two saturated PCM16 samples detected: not declared production-clean.

Offline faster-whisper small/int8/CPU, explicit Hebrew, beam5: second take transcribed all 15 original words exactly (punctuation ignored); first failed. Existing Brian recording used only as ASR positive control also matched all words; not synthesized again or used as a voice reference. ASR not proof of accent, subtle pronunciation, age, warmth, identity stability or native Hebrew. No human listening performed here. One built-in identity only: do not present seed/prosody variants as three distinct voices. No SSML or pronunciation lexicon demonstrated. No fixed narrator selected. Longer pronunciation and human listening gates remain.

Actual MP3 delivered privately: https://drive.google.com/file/d/1sw14_4mFy3f9mVd9i5sW9oxrHxMCoMoN/view . Scripts, requirements, original WAVs, checks, model pin and license archived privately (no weights/secrets): https://drive.google.com/file/d/18DVHv0f9D2jVPVcWAHYJkiKQ-u6b1gbd/view . External service charges: $0; workspace plan usage unknown. This establishes a free-to-run technical route, not an approved high-quality three-voice cast. No further model/payment setup required of owner to listen.


## Human rejection and deeper audit — 2026-11-04

Owner rejected Chatterbox: foreign accent, shaky/non-natural/unstable delivery despite exact ASR. Reject that take (263fb696fc56ff00b24f48cd69e0117a79d020c6c20bc413c47da2d6086626cd); do not resubmit cosmetic variants. No narrator selected. Root-cause distinctions, observed signal metrics, source-checked Mishnah audition and three alternative routes are in [narrator-quality-investigation.md](narrator-quality-investigation.md). No new Chatterbox, Avri, Andrew or Brian synthesis in this investigation.

MOSS v1.5 anonymous demo refused its requested 270s GPU allocation; no audio. OmniVoice anonymous voice-design demo produced one private 17.35s take, no cloning, then two local ASR passes flagged mismatches. Stronger Hebrew ASR recovered Rabban Gamliel correctly, illustrating that ASR mistakes are not pronunciation diagnoses. No human listening or quality approval for new take; CC-BY-NC model cannot be selected for commercial production on present evidence. Gemini's account free-only boundary remains unverified; prepared payloads not sent. No paid calls, subscriptions, account changes or production code changes.
