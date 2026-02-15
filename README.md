# Github Actions

Repository to store GitHub Actions &amp; workflows

## Reusable Workflows

| Workflow                                | Description                                                                          |
| --------------------------------------- | ------------------------------------------------------------------------------------ |
| `.github/workflows/tpl-terragrunt.yaml` | Terragrunt workflow template for managing terragrunt deployments with GitHub Actions |
| `.github/workflows/tpl-catalog-static-checks.yaml` | Static checks template for Terraform modules and Terragrunt units/stacks, including candidate version output |
| `.github/workflows/tpl-catalog-tag-release.yaml` | Release tagging template that tags `main` commits as `vYYYY.MM.DD-revX` |

## Actions

| Action                         | Description                                                                                                      |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `.github/actions/tg-summarize` | GitHub Action to summarize Terragrunt plan or apply steps and post the summary as a comment on the pull request. |
| `.github/actions/merge-pr`     | GitHub Action to automatically merge pull requests that meet specific criteria                                   |
