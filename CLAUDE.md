# github-actions — Shared Actions & Workflow Templates

## Purpose

Central library of reusable GitHub Actions (composite) and reusable workflow templates
(`workflow_call`) for the `proxmox-home-lab` organization. Every repo in the org that
runs CI/CD calls into this repo rather than duplicating pipeline logic.

Changes here affect all consumers — treat it like a shared library.

---

## Architecture

```
github-actions/
│
├── .github/actions/     Composite actions (single-step building blocks)
│                        Called with: uses: proxmox-home-lab/github-actions/.github/actions/<name>@<ref>
│
└── .github/workflows/   Reusable workflow templates (full job pipelines)
                         Called with: uses: proxmox-home-lab/github-actions/.github/workflows/<name>.yaml@<ref>
```

**Dependency chain for IaC deployments:**
```
consumer repo workflow
        │
        └─► tpl-terragrunt.yaml (workflow_call)
                  │
                  ├─► vault-secrets (action)   — loads Vault secrets into env
                  └─► tg-summarize (action)    — parses Terragrunt logs for PR/job summaries
```

**Job structure inside `tpl-terragrunt` (action=apply):**
```
setup job        — Vault token + GitHub App token
     │
plan-for-apply   — fresh plan from main, uploads artifact, writes job summary
     │
apply job        — environment: production (GitHub pauses here)
                   reviewer approves → applies with plan artifact
```

---

## Directory Structure

```
github-actions/
├── .github/
│   ├── actions/
│   │   ├── vault-secrets/
│   │   │   └── action.yml          # Installs Vault, fetches vault-helper.sh, loads secrets
│   │   ├── tg-summarize/
│   │   │   ├── action.yml          # Orchestrates summarize.py, posts PR comment
│   │   │   └── summarize.py        # Parses Terragrunt log output → markdown summary
│   │   └── merge-pr/
│   │       └── action.yml          # Wraps `gh pr merge` with configurable method
│   └── workflows/
│       ├── tpl-terragrunt.yaml     # IaC plan/apply pipeline (main template)
│       ├── tpl-release.yaml        # Semantic release pipeline
│       └── tpl-terraform-module.yaml  # Module validation + docs pipeline
└── README.md
```

---

## Key Files

| File | Description |
|------|-------------|
| `.github/workflows/tpl-terragrunt.yaml` | Main IaC template. `action: plan` → PR comment; `action: apply` → plan-for-apply + environment gate + apply |
| `.github/actions/vault-secrets/action.yml` | Downloads `vault-helper.sh` from the `.github` repo at runtime, sources it to inject secrets as masked env vars |
| `.github/actions/tg-summarize/action.yml` | Strips ANSI codes from Terragrunt logs, extracts per-unit summaries, enforces 60k-char limit, posts/updates PR comment or job summary |
| `.github/actions/tg-summarize/summarize.py` | Python parser for Terragrunt plan/apply output |
| `.github/actions/merge-pr/action.yml` | Wraps `gh pr merge` — retained for other use cases, no longer used in `tpl-terragrunt` |

---

## Development Workflow

### Calling `tpl-terragrunt` from another repo

The consumer repo needs two triggers: `pull_request` (for plan) and `push` to main
(for apply). The apply is gated by the `production` GitHub Environment — configure
it in the consumer repo's settings with required reviewers.

```yaml
# .github/workflows/terragrunt.yaml  (in consumer repo)
name: Terragrunt

on:
  pull_request:
    branches: [main]
    paths: ["iac/**"]
  push:
    branches: [main]
    paths: ["iac/**"]

permissions:
  contents: read
  pull-requests: write

jobs:
  plan:
    if: ${{ github.event_name == 'pull_request' }}
    uses: proxmox-home-lab/github-actions/.github/workflows/tpl-terragrunt.yaml@main
    with:
      action: plan
    secrets: inherit

  apply:
    if: ${{ github.event_name == 'push' }}
    uses: proxmox-home-lab/github-actions/.github/workflows/tpl-terragrunt.yaml@main
    with:
      action: apply
    secrets: inherit
```

The `apply` action triggers `plan-for-apply` + `apply` jobs. The `apply` job uses
`environment: production` — GitHub pauses it until a required reviewer approves.
Create the `production` environment in the consumer repo's Settings → Environments.

### Environment variables expected by `tpl-terragrunt`

The following must be available as repository/org secrets or variables in the consumer:

| Name | Type | Description |
|------|------|-------------|
| `VAULT_ADDR` | secret | Vault server URL |
| `VAULT_CLIENT_ID` | secret | AppRole Role ID |
| `VAULT_SECRET_ID` | secret | AppRole Secret ID |
| `VAULT_AGENT_CONFIG` | variable | Vault Agent HCL template (base64 or raw) |

GitHub App credentials are loaded from Vault by `vault-secrets` action and used to
create a scoped token via `actions/create-github-app-token`.

### Pinned tool versions (defaults in `tpl-terragrunt`)

| Tool | Default version | Env var to override |
|------|----------------|---------------------|
| Terragrunt | `v0.99.2` | `TG_VERSION` |
| OpenTofu | `v1.11.5` | `TOFU_VERSION` |
| Vault | `v1.20.2` | `VAULT_VERSION` |

Always pass versions as inputs/env vars. Never hardcode them inside actions.

### Testing locally

Use `act` (pre-installed in the devcontainer) to run workflows locally:

```bash
# Simulate a plan trigger
act pull_request \
  --secret-file .secrets \
  --var-file .vars \
  -W .github/workflows/tpl-terragrunt.yaml \
  -e event.json
```

---

## Commands Reference

| Command | Context |
|---------|---------|
| `act pull_request -W .github/workflows/<file>` | Run workflow locally with `act` |
| `act -l` | List available workflows and jobs |
| `gh workflow run <name>` | Manually trigger a workflow on GitHub |
| `gh run list --workflow=<name>` | List recent runs of a workflow |

---

## Conventions

**Composite actions:**
- Each action lives in its own directory under `.github/actions/<name>/`.
- `action.yml` must declare all `inputs` with `description` and `default` where applicable.
- Add `required: true` only for inputs with no sensible default.
- Use `${{ inputs.<name> }}` — never rely on environment variables implicitly.
- Scripts embedded in `run:` steps must use `set -euo pipefail`.

**Workflow templates (`tpl-*.yaml`):**
- All templates use `on: workflow_call` — they are not directly triggered.
- Tool versions come from `env:` block defaults, overridable by caller inputs.
- Jobs follow the two-phase pattern: `setup` (token creation) → `action` (plan or apply).
- Concurrency group must include repo name + PR/issue number to prevent conflicts across
  repos calling the same template simultaneously.

**Versioning:**
- Public actions use pinned major versions (`@v4`, `@v2`) — do not use `@latest`.
- Internal custom actions currently use `@main` — this is a known gap. Pin to semantic
  tags once a release pipeline is established via `tpl-release.yaml`.

---

## Dependencies

**Upstream (what this repo needs):**
- `proxmox-home-lab/.github` — `vault-helper.sh` is fetched at runtime from that repo.
  Version is controlled by `VAULT_HELPER_VERSION` env var (default: `main`).

**Downstream (what consumes this repo):**
- All repos in the org that run IaC — currently: `proxmox-home-lab/.github`.
- Future: any repo using `tpl-release` or `tpl-terraform-module`.

---

## Known Issues / TODOs

- [ ] **`@main` on internal action references** — `tpl-terragrunt.yaml` calls
  `vault-secrets`, `tg-summarize`, and `merge-pr` at `@main`. Migrate to semantic tags
  once `tpl-release` is wired up for this repo.
- [ ] **No workflow tests** — no `act`-based CI for validating templates before merge.
- [ ] **`VAULT_HELPER_VERSION: main`** — vault-helper.sh is fetched from the `.github`
  repo at `main`. Should pin to a tag alongside the other tool versions.
