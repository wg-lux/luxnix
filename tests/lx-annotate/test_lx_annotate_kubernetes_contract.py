from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
K8S_DIR = REPO_ROOT / "kubernetes/lx-annotate"


def _read(name: str) -> str:
    return (K8S_DIR / name).read_text(encoding="utf-8")


def _all_yaml() -> str:
    return "\n---\n".join(
        path.read_text(encoding="utf-8") for path in sorted(K8S_DIR.glob("*.yaml"))
    )


def test_lx_annotate_kustomization_lists_cluster_runtime_artifacts() -> None:
    source = _read("kustomization.yaml")

    for resource in [
        "web-deployment.yaml",
        "worker-deployment.yaml",
        "service.yaml",
        "ingress.yaml",
        "configmap.yaml",
        "secret.yaml",
        "pvc.yaml",
        "cronjobs.yaml",
    ]:
        assert f"  - {resource}" in source

    assert "migrate-job.yaml" not in source
    assert "load-base-data-job.yaml" not in source
    assert "  - bootstrap-job.yaml" not in source
    assert "Run bootstrap-job.yaml explicitly" in source


def test_lx_annotate_kubernetes_web_worker_and_migration_shapes_exist() -> None:
    source = _all_yaml()

    assert "kind: Deployment" in source
    assert "name: lx-annotate-web" in source
    assert "name: lx-annotate-worker-maintenance" in source
    assert "name: lx-annotate-worker-pipeline" in source
    assert "name: lx-annotate-worker-frame-extraction" in source
    assert "name: lx-annotate-worker-inference" in source
    assert "name: lx-annotate-worker-training" in source
    assert "replicas: 0" in source
    assert "kind: Job" in source
    assert "generateName: lx-annotate-bootstrap-" in source
    assert "name: lx-annotate-migrate" not in source
    assert "name: lx-annotate-load-base-data" not in source
    assert "kind: Service" in source
    assert "kind: Ingress" in source
    assert "kind: PersistentVolumeClaim" in source
    assert "name: lx-annotate-data" in source


def test_lx_annotate_kubernetes_uses_external_services_and_shared_secrets() -> None:
    source = _all_yaml()
    cronjobs = _read("cronjobs.yaml")

    assert "postgres.lx-annotate.svc.cluster.local" in source
    assert "rediss://redis.lx-annotate.svc.cluster.local:6379/1" in source
    assert "CELERY_DEFAULT_QUEUE: default" in source
    assert "CELERY_PIPELINE_QUEUE: pipeline" in source
    assert "CELERY_FRAME_EXTRACTION_QUEUE: frame_extraction" in source
    assert "CELERY_INFERENCE_QUEUE: inference" in source
    assert 'CELERY_FRAME_EXTRACTION_REQUIRE_SECURE_TRANSPORT: "true"' in source
    assert 'CELERY_BROKER_SECURE_TRANSPORT_CONFIRMED: "false"' in source
    assert "VIDEO_TEMPORAL_INFERENCE_JOB_MODE: celery" in source
    assert "LX_ANNOTATE_MASTER_KEY_FILE: /run/secrets/lx-annotate/master-key" in source
    assert "secretName: lx-annotate-secret" in source
    assert "key: master-key" in source
    assert cronjobs.count("key: DJANGO_SECRET_KEY") >= 4
    assert cronjobs.count("key: DJANGO_DB_PASSWORD") >= 4
    assert "mountPath: /var/lib/lx-annotate/data" in source


def test_lx_annotate_kubernetes_web_probes_and_resources_are_declared() -> None:
    web = _read("web-deployment.yaml")
    worker = _read("worker-deployment.yaml")

    assert "startupProbe:" in web
    assert "readinessProbe:" in web
    assert "wait-for-bootstrap" in web
    assert "release-${LX_ANNOTATE_RELEASE_ID}.ready" in web
    assert "wait-for-bootstrap" in worker
    assert "release-${LX_ANNOTATE_RELEASE_ID}.ready" in worker
    assert "tcpSocket:" in web
    assert "resources:" in web
    assert "requests:" in web
    assert "limits:" in web
    assert "resources:" in worker
    assert "celery -A lx_annotate.celery:app worker" in worker
    assert '--queues="${CELERY_MAINTENANCE_QUEUE},${CELERY_DEFAULT_QUEUE}"' in worker
    assert '--queues="${CELERY_PIPELINE_QUEUE}"' in worker
    assert '--queues="${CELERY_FRAME_EXTRACTION_QUEUE}"' in worker
    assert '--queues="${CELERY_INFERENCE_QUEUE}"' in worker
    assert '--queues="${CELERY_TRAINING_QUEUE}"' in worker
    assert "--prefetch-multiplier=1" in worker


def test_lx_annotate_kubernetes_release_is_consistent() -> None:
    source = _all_yaml()

    assert 'LX_ANNOTATE_RELEASE_ID: "0.5.1"' in source
    assert "ghcr.io/wg-lux/lx-annotate:0.4.6" not in source
    assert source.count("ghcr.io/wg-lux/lx-annotate:0.5.1") >= 10


def test_lx_annotate_kubernetes_singleton_batch_workloads_forbid_overlap() -> None:
    cronjobs = _read("cronjobs.yaml")
    bootstrap = _read("bootstrap-job.yaml")

    assert cronjobs.count("kind: CronJob") >= 4
    assert cronjobs.count("concurrencyPolicy: Forbid") >= 4
    assert cronjobs.count("release-${LX_ANNOTATE_RELEASE_ID}.ready") >= 4
    assert "run_filewatcher" in cronjobs
    assert "--process-existing-once" in cronjobs
    assert "import_sap_ish_zip" in cronjobs
    assert "export-frames" in cronjobs
    assert "migrate_media_storage" in cronjobs
    assert "generateName: lx-annotate-bootstrap-" in bootstrap
    assert "namespace: lx-annotate" in bootstrap
    assert bootstrap.index("migrate --noinput") < bootstrap.index("load_base_db_data")
