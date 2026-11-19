# eks-multiregion-apps

The application's source code and the pipeline that turns it into container images. Nothing
here knows about clusters or environments.

Related repositories: `eks-multiregion-gitops` decides which version runs in dev, stg and prd.
`eks-multiregion-infra` builds the clusters.

## Layout

```
frontend/                frontend tier: a static page served by nginx, which forwards /api/
                         to the backend. Image: demo-web
backend/                 backend tier: a small JSON API in Python. The only tier that talks
                         to the database. Image: demo-api
.github/workflows/ci.yml the pipeline
ci-equivalents/          the same pipeline as a Jenkinsfile and for Bitbucket Pipelines
```

The third tier, the database, is RDS PostgreSQL, created by Terraform in the infra repository.

## The pipeline

| When | What runs |
| --- | --- |
| Pull request | Unit tests, build both images, scan them with Trivy |
| Merge to `main` | The same, then push both images to ECR in both regions, then ask the GitOps repository to release the version to dev |

**Build once.** Both images are tagged with the commit (`a1b2c3d`) and pushed one time. ECR
tags are immutable. dev, stg and prd all run these exact images: promoting a version means
changing a tag in the GitOps repository, never rebuilding.

The pipeline signs in to AWS with OIDC (no stored keys) and may only push to the two image
repositories. It holds no cluster credentials. Its last step starts the GitOps repository's
`promote` workflow for dev; it has no say over stg or prd.

## The backend's endpoints

| Path | What |
| --- | --- |
| `/api/info` | Which version, environment, region and pod answered, and whether its secrets are loaded |
| `/api/visits` | `GET` reads the visit count from the database; `POST` adds one |
| `/api/burn?ms=400` | Uses CPU, to exercise the autoscalers |
| `/healthz`, `/readyz` | Liveness and readiness probes |

Database settings and secrets arrive as files under `/secrets` (from Vault, through External
Secrets). With no database configured, the count is kept in memory, so the service runs on a
laptop with nothing else installed.

## Run it locally

```
cd backend && python3 -m unittest -v
PORT=8081 python3 server.py &                 # the backend
docker build -t demo-web:local frontend
docker run --rm --network host -e BACKEND_URL=http://127.0.0.1:8081 demo-web:local
# open http://localhost:8080
```

## Secrets and variables on GitHub

- secret `AWS_PUBLISH_ROLE_ARN`: from the infra repository's bootstrap output
- secrets `RELEASE_BOT_APP_ID`, `RELEASE_BOT_PRIVATE_KEY` and variable `GITOPS_REPO_NAME`:
  see the GitOps repository's README
