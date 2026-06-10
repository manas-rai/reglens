# AWS Deployment Plan

Cost-optimized deployment for the RegLens Phase 1 demo. Goal: a single
public URL that runs the full pipeline (FastAPI + LangGraph supervisor +
two ADK agents + Postgres + UI) for under ~$40/mo at idle.

## Target topology

```
┌───────────────────────────────────────────────────────────────────┐
│ Route53 ──► CloudFront ──► S3 (Next.js static export)             │ UI
│                                                                   │
│ Route53 ──► ALB ──► Fargate task (4 containers, localhost net) ──┐│ API
│                                                                  ││
│                              ┌──── api:8000 ────────┐            ││
│                              ├──── langgraph:8010 ──┤            ││
│                              ├──── adk-ingest:8001 ─┤            ││
│                              └──── adk-risk:8002 ───┘            ││
│                                                                   │
│             ┌─────────────────────────────────────────────────┐   │
│             │  RDS Postgres 16 (db.t4g.micro, pgvector)       │   │ DB
│             └─────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

### Why a single multi-container Fargate task

The compose file already wires the four backend services to talk over
service names. In a single Fargate task all four containers share a
network namespace, so service names become `localhost:PORT` with zero
service-discovery setup. Restarts are coupled — fine for a demo, and
~3× cheaper than running four separate Fargate services.

### Components

| Concern               | AWS resource                            | Notes                                    |
| --------------------- | --------------------------------------- | ---------------------------------------- |
| Container images      | ECR (one repo per Dockerfile)           | `api`, `langgraph`, `adk` (shared)       |
| Compute               | 1× Fargate Spot task (0.5 vCPU, 2 GB)   | 4 app containers in one task definition  |
| Database              | RDS Postgres 16, db.t4g.micro, 20 GB    | Single-AZ, 7-day backups, pgvector ext   |
| Object/static hosting | S3 (private) + CloudFront (OAC)         | Hosts Next.js `output: "export"` bundle  |
| TLS + routing         | ACM cert + ALB                          | One HTTPS listener, `/api/*` → Fargate   |
| Secrets               | SSM Parameter Store (`SecureString`)    | Gemini/Anthropic API keys, app API key   |
| Logs                  | CloudWatch Logs (one log group per ctn) | 14-day retention                         |
| State / network       | New VPC, 2 public + 2 private subnets   | Fargate in private, RDS in private       |
| Region                | TBD — see open questions                |                                          |

### Estimated monthly cost

| Item                              | $/mo |
| --------------------------------- | ---: |
| Fargate Spot 0.5 vCPU / 2 GB 24×7 |  ~$6 |
| RDS t4g.micro + 20 GB gp3         | ~$15 |
| ALB                               | ~$18 |
| CloudFront + S3 (low traffic)     |  ~$1 |
| NAT (single small NAT instance)   |  ~$4 |
| Misc (logs, ECR storage)          |  ~$2 |
| **Total**                         | **~$46** |

NAT instance (vs NAT gateway) is the biggest knob; gateway is ~$32/mo.
We use a NAT instance to keep idle cost low for a demo.

## Repo layout

```
infra/
  terraform/
    main.tf
    variables.tf
    outputs.tf
    versions.tf
    modules/
      network/        # VPC, subnets, NAT instance, SGs
      ecr/            # 3 ECR repos
      rds/            # postgres + pgvector init
      fargate/        # task def + service + ALB
      ui/             # S3 + CloudFront
    envs/
      demo.tfvars
```

Plus one `Dockerfile` for the UI bundle build step in CI (we still use
S3 static export for the runtime; the Dockerfile is just for `next
build` reproducibility in CI/CD).

## Phased rollout

1. **Phase A — Foundation** (PR 1)
   - `infra/terraform/` skeleton, VPC module, ECR module
   - GitHub Actions: build + push the three images to ECR on `main`
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

## Open questions for the operator

These have to be answered before phase A:

1. **AWS account** — fresh dedicated account, or shared with other work?
2. **Region** — `us-east-1` (cheapest, default for CloudFront), `ap-south-1` (closer to India for low-latency), or other?
3. **Domain** — bring an existing domain into Route53, register a new one, or skip Route53/ACM and use the ALB DNS + CloudFront default URL (no HTTPS to API)?
4. **Cost ceiling** — is ~$46/mo at idle acceptable, or do we need an auto-stop schedule (off at night/weekend)?
5. **CI/CD** — push to ECR + deploy on every `main` merge, or manual `terraform apply` + image promote?

## Out of scope for this demo

- Multi-AZ RDS / read replicas
- Autoscaling (a single 24×7 task is enough for the demo)
- WAF, Shield Advanced, GuardDuty
- VPC endpoints (we accept NAT cost as the simpler option)
- LangSmith / external observability beyond CloudWatch
