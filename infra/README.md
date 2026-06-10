# RegLens infra

Terraform for the AWS demo deployment. Architecture and phasing:
[docs/AWS_DEPLOYMENT_PLAN.md](../docs/AWS_DEPLOYMENT_PLAN.md).

Everything after the one-time bootstrap runs through GitHub Actions
(`.github/workflows/terraform.yml` and `build-images.yml`) using OIDC — no AWS
keys are stored in GitHub.

## One-time bootstrap (local, admin credentials)

```bash
cd infra/terraform/bootstrap
terraform init
terraform apply
```

This creates the Terraform state bucket, the GitHub OIDC provider, and
the `reglens-github-actions` CI role. Then:

1. Copy the `account_id` output and set it as a **repository variable**
   named `AWS_ACCOUNT_ID` (GitHub → Settings → Secrets and variables →
   Actions → Variables).
2. Create the approval gate: GitHub → Settings → Environments → New
   environment → name it `aws-demo` → enable **Required reviewers** and
   add yourself. The apply job pauses on this environment until approved.
3. Commit nothing — bootstrap state stays local (`*.tfstate` is
   gitignored). It changes rarely; re-run `terraform apply` here if it
   ever needs updating.

## Day-to-day

- **PR touching `infra/terraform/`** → CI runs fmt check, validate, and
  `terraform plan`; review the plan in the job log before merging.
- **Merge to `main`** → the plan job re-runs, then the apply job waits
  on the `aws-demo` environment — approve it in the run page (Review
  deployments → aws-demo → Approve) and it applies.
- **Merge touching `src/`, `docker/`, or deps** → CI builds the three
  images (`api`, `langgraph`, `adk`) and pushes `:latest` + `:<sha>` to
  ECR.

## Local plan (optional)

```bash
cd infra/terraform
cp backend.hcl.example backend.hcl   # fill in your account id
terraform init -backend-config=backend.hcl
terraform plan
```

Prefer letting CI apply; a local apply and a CI apply racing each other
is prevented by S3 state locking but still confusing.

## Security tradeoffs (demo-grade, revisit before production)

- The CI role has `AdministratorAccess` — see the comment in
  `bootstrap/main.tf`.
- The Fargate task runs in a public subnet with a public IP (no NAT);
  inbound is restricted to the ALB by security group.
- The ALB listener is plain HTTP until a domain + ACM cert exist
  (Phase E).
