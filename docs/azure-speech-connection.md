# Protected Azure Speech connection

Preparation only. No connection, F0 verification or speech has run yet. Do not merge automatically.

Create environment `azure-speech` at https://github.com/barkinam21-pixel/project-mishna/settings/environments . Restrict deployment branches to `main` and require the owner as reviewer; prevent self-review where available. If protection is unavailable, do not configure secrets or run. Workflow accepts only manual main-branch runs, never PR events. Review main's workflow/code before approval. Maintainers able to modify approved code remain trusted.

Environment secrets:
- AZURE_SPEECH_KEY: Azure Portal → existing Speech resource → Resource Management → Keys and Endpoint → a current, unexposed KEY. Rotate the key previously pasted in chat first. Never send keys in chat.
- AZURE_SPEECH_REGION: same page → Location/Region (API value, such as eastus; do not assume this example is yours).

A key cannot prove resource pricing. Use a federated Azure identity, no client secret. Azure Portal → Microsoft Entra ID → App registrations → existing or dedicated application → Certificates & secrets → Federated credentials → GitHub Actions, repository barkinam21-pixel/project-mishna, environment azure-speech. Issuer https://token.actions.githubusercontent.com, audience api://AzureADTokenExchange, subject repo:barkinam21-pixel/project-mishna:environment:azure-speech. Grant this identity Reader scoped only to the existing Speech resource (no pricing/write permission).

Environment variables:
- AZURE_CLIENT_ID / AZURE_TENANT_ID: App registration → Overview → Application (client) ID / Directory (tenant) ID.
- AZURE_SUBSCRIPTION_ID: Speech resource → Overview → Subscription ID.
- AZURE_SPEECH_RESOURCE_ID: Speech resource → Properties → Resource ID.

Portal → resource → Pricing tier must show F0. The runner independently reads ARM each time and checks F0, SpeechServices kind and matching region before contacting the synthesis endpoint. No pricing changes. First run with synthesize=false: live ARM + authenticated Hebrew voice-list check, no audio. Later synthesize=true sends one short request, no retries or system-voice fallback. F0 quota exhaustion fails; it does not switch to S0. Audition uses Avri/he-IL SSML, not English RPGM styles. No claim of naturalness until listening.

Only encrypted audio is uploaded, using the existing project public key. The matching private key must remain private; its prior documented Library location is not currently accessible to this agent. A successful encrypted artifact alone is not a directly playable delivery; authorized private decryption is required. No new voice sample exists yet.
