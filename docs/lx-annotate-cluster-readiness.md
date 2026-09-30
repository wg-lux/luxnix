# lx-annotate Cluster Readiness Review

Reviewed: 2026-05-06

## Verdict

The repo now has cluster-oriented scaffolding, but `lx-annotate` should not be
called cluster-ready yet.

The implemented work is enough to validate split NixOS runtime roles, external
service configuration, shared runtime-data assumptions, and a first Kubernetes
deployment shape. The remaining work is runtime proof: multi-worker behavior,
real health checks, and an operator-tested release flow.

## Implemented Contracts

### NixOS Runtime Split

- `lx-annotate-boot.service` stays web-only in wheel mode.
- `lx-annotate-migrate.service` runs wheel-mode database migrations.
- `lx-annotate-load-base-data.service` runs wheel-mode base-data loading after
  migrations.
- `lx-annotate-celery-worker.service` runs asynchronous Celery processing.
- Watcher, SAP import, export, and media migration remain explicit singleton
  services, timers, or batch commands.
- `runtime.limits` applies to the web service.
- `runtime.workerLimits` applies independently to the Celery worker.

### Cluster Guardrails

Cluster-oriented validation is opt-in through:

- `runtime.clustered.enable = true`
- `runtime.externalServices.redisUrl`
- `runtime.externalServices.postgresHost`
- `runtime.externalServices.postgresPort`
- `runtime.clustered.sharedStorage = true`
- `runtime.clustered.sharedMasterKeyFile`
- `runtime.autoGenerateMasterKey = false`

With clustered mode enabled, evaluation fails closed for local Redis/Postgres,
missing shared-storage acknowledgement, per-host encrypted-data management, and
hostname-scoped Vault encrypted-data state. `runtime.masterKeyFile` must resolve
to the same path as `runtime.clustered.sharedMasterKeyFile`.

### Kubernetes Package

The first Kubernetes package lives at `kubernetes/lx-annotate` and includes:

- `Deployment/lx-annotate-web`
- `Deployment/lx-annotate-worker`
- `Service/lx-annotate-web`
- `Ingress/lx-annotate`
- `ConfigMap/lx-annotate-config`
- `Secret/lx-annotate-secret`
- `PVC/lx-annotate-data` with `ReadWriteMany`
- suspended singleton CronJobs for file watcher, SAP import, export, and media
  migration with `concurrencyPolicy: Forbid`
- `bootstrap-job.yaml` as an explicit per-release Job using
  `metadata.generateName`

`bootstrap-job.yaml` is intentionally not part of `kustomization.yaml`. Apply
the steady-state resources with Kustomize, then create the bootstrap Job
explicitly for each release. Web, worker, and CronJob pods wait for the release
marker at:

```text
${LX_ANNOTATE_BOOTSTRAP_MARKER_DIR}/release-${LX_ANNOTATE_RELEASE_ID}.ready
```

## Required Release Flow

1. Update the image tag in the Kubernetes manifests.
2. Update `LX_ANNOTATE_RELEASE_ID` in `configmap.yaml` to a new value for the
   release.
3. Apply the steady-state resources from `kubernetes/lx-annotate`.
4. Create `kubernetes/lx-annotate/bootstrap-job.yaml` explicitly.
5. Wait for the bootstrap Job to finish and write the release marker.
6. Let web and worker pods pass their init gate.
7. Unsuspend singleton CronJobs only when the shared storage and input locations
   are ready.

If `LX_ANNOTATE_RELEASE_ID` is reused, an old marker can allow pods through
without rerunning migrations and base-data loading for the new image.

## Review Findings

- Kubernetes readiness is currently a TCP socket check. It verifies that the web
  port accepts connections, but it does not prove database, Redis, or shared
  storage availability.
- The Kubernetes package references external Postgres and Redis endpoints but
  does not provide those services. That is acceptable for a cluster package, but
  the target environment must supply them before rollout.
- Web and worker deployments currently start with one replica each. Multi-worker
  correctness still needs to be proven by scaling workers and running real queue
  workloads.
- CronJobs are `suspend: true` by default. That is a safe default, but operators
  must deliberately enable the intended singleton jobs after bootstrap.
- Secrets in `secret.yaml` are placeholders. Production rollout needs a real
  secret-management path for Django, database, OIDC, and the shared workload
  master key.

## Remaining Gates

Call this cluster-ready only after these checks pass:

1. One web process plus one Celery worker processes a representative job.
2. Two or more worker processes process the same workload without duplicate
   processing.
3. Redis, Postgres, shared storage, and shared master key are external/shared in
   the deployed environment.
4. The generated bootstrap Job is run once per release before web and worker
   pods pass their init gate.
5. Health/readiness endpoints reflect database, Redis, and storage availability.
6. Worker tasks are audited for idempotency, locking, retries, and cleanup
   races.
7. Kubernetes rollout and rollback are tested with changed image tags and
   changed `LX_ANNOTATE_RELEASE_ID` values.
