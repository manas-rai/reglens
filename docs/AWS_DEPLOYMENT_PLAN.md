# AWS Deployment Plan

Cost-optimized deployment for the RegLens Phase 1 demo. Goal: a single
public URL that runs the full pipeline (FastAPI + LangGraph supervisor +
two ADK agents + Postgres + UI) for ~$42/mo at idle.

## Decisions (confirmed 2026-06-10)

1. **Account** — existing AWS account (all resources tagged `Project=reglens` for cost attribution and teardown).
2. **Region** — `ap-south-1` (Mumbai).
3. **Domain** — none for now; ALB DNS name for the API, CloudFront default URL for the UI. Phase E adds Route53/ACM later if wanted.
4. **Cost** — ~$42/mo at idle accepted; no auto-stop schedule.
5. **CI/CD** — everything through GitHub Actions: image build + push to ECR, and `terraform plan` (PRs) / `terraform apply` (main, gated behind a required-reviewer approval on the `aws-demo` GitHub environment). Auth via GitHub OIDC — no long-lived AWS keys in repo secrets. One-time local bootstrap creates the state bucket and the OIDC role.

## Target topology

```
┌───────────────────────────────────────────────────────────────────┐
│ CloudFront ──► S3 (Next.js static export)                         │ UI
│                                                                   │
│ ALB ──► Fargate task (4 containers, localhost net, public subnet) │ API
│                                                                   │
│                ┌──── api:8000 ────────┐                           │
│                ├──── langgraph:8010 ──┤                           │
│                ├──── adk-ingest:8001 ─┤                           │
│                └──── adk-risk:8002 ───┘                           │
│                                                                   │
│             ┌─────────────────────────────────────────────────┐   │
│             │  RDS Postgres 16 (db.t4g.micro, pgvector)       │   │ DB
│             │  isolated subnets, no internet route            │   │
│             └─────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

### Why a single multi-container Fargate task

The compose file already wires the four backend services to talk over
service names. In a single Fargate task all four containers share a
network namespace, so service names become `localhost:PORT` with zero
service-discovery setup. Restarts are coupled — fine for a demo, and
~3× cheaper than running four separate Fargate services.

### Why no NAT

The Fargate task runs in a **public subnet with a public IP**, so it
pulls ECR images and reaches the Gemini/Anthropic APIs straight through
the internet gateway — no NAT instance or gateway needed. Inbound
traffic still only enters via the ALB (the task security group accepts
port 8000 from the ALB security group only). RDS sits in isolated
subnets with no internet route at all. This trades a textbook
private-subnet layout for ~$4–32/mo saved and one less moving part —
the right trade for a demo.

### Components

| Concern               | AWS resource                            | Notes                                    |
| --------------------- | --------------------------------------- | ---------------------------------------- |
| Container images      | ECR (one repo per Dockerfile)           | `api`, `langgraph`, `adk` (shared)       |
| Compute               | 1× Fargate Spot task (0.5 vCPU, 2 GB)   | 4 app containers in one task definition  |
| Database              | RDS Postgres 16, db.t4g.micro, 20 GB    | Single-AZ, 7-day backups, pgvector ext   |
| Object/static hosting | S3 (private) + CloudFront (OAC)         | Hosts Next.js `output: "export"` bundle  |
| Routing               | ALB (HTTP listener on ALB DNS name)     | HTTPS added in Phase E with a domain     |
| Secrets               | SSM Parameter Store (`SecureString`)    | Gemini/Anthropic API keys, app API key   |
| Logs                  | CloudWatch Logs (one log group per ctn) | 14-day retention                         |
| Network               | New VPC, 2 public + 2 isolated subnets  | ALB + Fargate public, RDS isolated       |
| CI/CD auth            | GitHub OIDC provider + IAM role         | Bootstrapped once locally                |
| TF state              | S3 bucket with native lockfile          | Bootstrapped once locally                |
| Region                | `ap-south-1` (Mumbai)                   |                                          |

### Estimated monthly cost

| Item                              | $/mo |
| --------------------------------- | ---: |
| Fargate Spot 0.5 vCPU / 2 GB 24×7 |  ~$6 |
| RDS t4g.micro + 20 GB gp3         | ~$15 |
| ALB                               | ~$18 |
| CloudFront + S3 (low traffic)     |  ~$1 |
| Misc (logs, ECR storage)          |  ~$2 |
| **Total**                         | **~$42** |

The ALB is the biggest fixed cost. If we later want to cut it, the
fallback is exposing the Fargate task's public IP directly (changes on
every restart — acceptable only with a dynamic-DNS hack, so not now).

## Repo layout

```
infra/
  terraform/
    bootstrap/        # run ONCE locally: state bucket, OIDC provider, CI role
    main.tf           # root stack, applied by GitHub Actions
    variables.tf
    outputs.tf
    versions.tf
    backend.hcl.example
    modules/
      network/        # VPC, subnets, IGW, SGs
      ecr/            # 3 ECR repos
      rds/            # postgres + pgvector init        (Phase B)
      fargate/        # task def + service + ALB        (Phase C)
      ui/             # S3 + CloudFront                 (Phase D)
.github/
  workflows/
    images.yml        # build + push api/langgraph/adk images on main
    terraform.yml     # fmt+validate+plan on PR, apply on main
```

## Phased rollout

1. **Phase A — Foundation** (PR 1)
   - One-time local bootstrap: TF state bucket, GitHub OIDC provider, CI role
   - `infra/terraform/` skeleton, VPC module, ECR module
   - GitHub Actions: build + push the three images to ECR on `main`;
     terraform plan on PR, apply on `main`
2. **Phase B — Stateful** (PR 2)
   - RDS module (pgvector via `rds_force_ssl=0`, `shared_preload_libraries=vector`)
   - Migration job: one-shot ECS task that runs `alembic upgrade head`
3. **Phase C — Compute** (PR 3)
   - Fargate task def with 4 containers + ALB
   - Secrets wired from SSM into task env
4. **Phase D — UI** (PR 4)
   - `next.config.ts` static export
   - S3 + CloudFront module
   - Build + sync from GitHub Actions
5. **Phase E — DNS + TLS** (PR 5)
   - ACM cert + Route53 records
   - Health checks, alarms

## Out of scope for this demo

- Multi-AZ RDS / read replicas
- Autoscaling (a single 24×7 task is enough for the demo)
- WAF, Shield Advanced, GuardDuty
- VPC endpoints (public-subnet task makes them unnecessary)
- Custom domain / HTTPS on the ALB (Phase E, if ever)
- LangSmith / external observability beyond CloudWatch
