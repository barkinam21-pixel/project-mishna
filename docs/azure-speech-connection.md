# Azure Speech — shortest protected setup

Status: owner reports azure-speech environment created, owner required reviewer, main-only protections, and Portal F0 verified. Connector cannot read environment metadata (unsupported endpoint), and shell proxy is unavailable. Independent verification has NOT run. No screenshots or keys requested. PR #38 remains open; no merge authorized.

## 1. Azure identity in one Portal form, no commands

[Open the pinned identity setup form](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fbarkinam21-pixel%2Fproject-mishna%2F7fe7cc37caf6386d43f70369e2dd8adb96f1d0b8%2Finfrastructure%2Fazure-speech-identity.json)

Choose the Speech resource's existing subscription and existing resource group. Enter its exact existing resource name in Speech Resource Name. Leave Identity Name unchanged unless that name is already used for a different purpose. Review + create. Do not create a Speech resource or change its tier.

The template creates only: a user-assigned managed identity, a GitHub federated credential restricted to repo barkinam21-pixel/project-mishna environment azure-speech, and Reader scoped to the existing Speech resource. No role at subscription or resource-group scope, no app password, no key lookup permission. Identity resources have no added service charge per Microsoft; no compute/storage/inference is created. Owner/role-assignment permission on that resource is needed to deploy. The template is structurally tested; live ARM deployment/validation requires your authorized Azure session and has not been performed here.

After deployment: Outputs → AZURE_CONNECTION → copy the JSON value (clientId, tenantId, subscriptionId, resourceId).

## 2. GitHub — two values, not seven

[Open azure-speech settings](https://github.com/barkinam21-pixel/project-mishna/settings/environments).

- Environment variables → Add environment variable → name AZURE_CONNECTION → paste the output JSON value. These are IDs, not credentials. Existing individual AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, AZURE_SPEECH_RESOURCE_ID remain supported if already set.
- Environment secrets → Add environment secret → name AZURE_SPEECH_KEY → paste a current UNEXPOSED key from the SAME F0 Speech resource → Keys and Endpoint. Never paste keys into chat. No action needed if the correct unexposed key is already stored.
- Region is now derived from live ARM metadata if AZURE_SPEECH_REGION is absent. Existing region secret remains supported and must match. No need to copy another value.

Keep Required reviewer = owner, explicit deployment branch main only, and administrator bypass disabled. For a sole owner who starts and approves the run, Prevent self-review must be OFF; otherwise that owner cannot approve their own request. This corrects the earlier generic self-review advice. Do not weaken the main-only boundary.

## 3. Review/merge before execution

[PR #38](https://github.com/barkinam21-pixel/project-mishna/pull/38) is not on main. A new manual workflow must exist on the default branch, and the job explicitly refuses other branches. Thus no Azure audition can run from the current PR. Do not temporarily allow PR branches or use pull_request_target. Merge only after explicit owner approval and successful checks on the final head.

After authorized merge: [Azure check workflow](https://github.com/barkinam21-pixel/project-mishna/actions/workflows/azure-speech-check.yml) → Run workflow on main, synthesize=false → review/approve pending azure-speech deployment. A metadata-only job checks owner-review, branch restriction and bypass settings before the protected job is eligible. If GitHub denies that metadata read, it stops instead of releasing Speech secrets; this read has not yet been exercised live.

The Azure job uses OIDC, reads live ARM metadata, matches resource ID/kind/region/F0, then checks the Hebrew voice list. It neither changes pricing nor infers F0 from a key. Portal confirmation is recorded but is not substituted for live gate verification. Always copy the key from that SAME verified resource.

After the successful connection-only run, synthesize=true requests exactly one short Avri audition with Hebrew SSML, no retry or fallback. F0 quota errors stop; never switch to S0. The request is not an approved performance or an episode master. Only ciphertext is uploaded. This short audition uses the existing session public key: its matching private key has been checked locally (not printed/uploaded), so a returned artifact can be decrypted here without asking for a Library key. Long-term key retention across environment loss is not guaranteed; preserve delivered decrypted audition privately when generated.

Current results: preparation only, no deployment, Azure login, key use, audition, new charges, merge or film publication. Platform quota usage unknown.

References: [Microsoft Portal deployment buttons](https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/deploy-to-azure-button), [managed identity federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust-user-assigned-managed-identity), [identity pricing](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview).
