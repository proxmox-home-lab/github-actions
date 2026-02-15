# Github Actions

Repository to store GitHub Actions &amp; workflows

## Reusable Workflows

| Workflow                                | Description                                                                          |
| --------------------------------------- | ------------------------------------------------------------------------------------ |
| `.github/workflows/tpl-terragrunt.yaml` | Terragrunt workflow template for managing terragrunt deployments with GitHub Actions |

## Actions

| Action                          | Description                                                                                                      |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `.github/actions/tg-summarize`  | GitHub Action to summarize Terragrunt plan or apply steps and post the summary as a comment on the pull request. |
| `.github/actions/merge-pr`      | GitHub Action to automatically merge pull requests that meet specific criteria                                   |
| `.github/actions/vault-secrets` | GitHub Action to load secrets from Vault and set them as environment variables for subsequent steps.             |
