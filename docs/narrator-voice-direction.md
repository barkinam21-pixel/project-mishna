# Main narrator: audition direction, not approved casting

Bar requests an Israeli Hebrew narrator perceived around 55–65: warm, wise, kind, patient, moderately deep, quietly lively and clear. Avoid frailty, rasp, fatigue, exaggerated old age or monotony. The narrator is a separate contemporary guiding voice, not a named Tanna or an impersonation of a historical sage. Elder character voices remain separately cast; no character voice is approved by this experiment.

The working Avri sample remains preserved and the default is unchanged. An optional comparison uses the same original generic audition text for both takes, avoiding unapproved Mishnah variants or historical claims. Baseline: Avri, rate -3%, default pitch. Candidate: same Avri, rate -6%, pitch -3%, default volume. These are experimental engineering choices, not a guarantee of age, warmth or human identity. No pitch-shifting postprocessing, cloning, unsupported expressive style or paid voice service.

Azure SSML supports rate and pitch, but support and perceived effect must be confirmed in the actual voice output: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice . No claim that Avri has a dedicated elderly/warm style.

The existing main-only, owner-dispatched, F0-verified and encrypted workflow gains compare_narrator=false by default. With synthesize=true and compare_narrator=true it issues exactly two short requests, with no retries. Both WAV files must decode correctly before the ciphertext is uploaded. Failure on either stops the comparison. No permanent narrator default changes. F0 remaining quota is unknown; a quota error must stop rather than change pricing.

Human review compares intelligibility, pronunciation, friendliness, energy, age impression, pitch continuity and distinction from elder characters. The reference sample is https://drive.google.com/file/d/1zUWMsuuiyN7oupgRzT7HkSF6p4cdSamV/view . Approval of the connection is not approval of the voice performance.
