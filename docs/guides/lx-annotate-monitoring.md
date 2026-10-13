# LX-Annotate operational timing and monitoring

**Schema version:** 1

**Feature:** `feature-tracking/lx_annotate_operational_monitoring.yml`

## Web resilience

**Ownership:** LuxNix wheel wrapper and systemd web unit

### Build gate

**Validator:** `modules/nixos/services/lx-annotate-local/scripts/wheel-static-check.py`

#### Behavior

- Validate the exact selected wheel before its runtime package can build.
- Require the src/main.ts Vite entry point, referenced files, CSS, assets, and resolved static and dynamic imports.
- Reject missing, empty, malformed, or escaping asset references without manufacturing a manifest.

**Limitation:** This asset gate does not replace installed-wheel Django smoke tests or migration compatibility review.

### Startup gate

- Discover the installed distribution through metadata without importing Django or mixing startup logs into the returned directory.
- Validate readable installed assets as the service user before rsync can change the served tree.
- Preserve existing served assets when candidate validation fails; partial copy failures still require repair.

### Process recovery

**Restart:** always

**Restart delay seconds:** 30

**Start rate limit:** disabled

**OOM policy:** stop

#### Behavior

- Unexpected clean exits and process failures retry without a permanent start-limit latch.
- An OOM kill stops the remaining web process group so systemd can restart it.
- Explicit systemctl stop remains effective; this policy does not override operator stops.
- Web uses normal nice, IO priority, and OOM adjustment while retaining configured CPU and memory limits.

#### Limitations

- Failed prerequisite jobs, missing mounts, invalid secrets, and failed migrations still block startup and require diagnosis.
- Restart policy is not application readiness and does not detect a live but hung web master.
- Worker retries and task idempotency are separate application contracts; no active task is killed merely for age.

### Rollout

- Build the runtime package and evaluate the selected host with locked inputs before deployment.
- Review the candidate release against the deployed release and schema before activating through the documented deployment workflow.
- Verify TLS frontend, manifest and referenced asset, authenticated readiness, and five minutes of stable restart count.
- Exercise clean exit and OOM recovery in an isolated service test before claiming runtime failure-injection coverage.

## Ownership

### Application

- Emit typed workflow and task timing with monotonic in-process durations.
- Classify outcomes and phases without sensitive or unbounded metric labels.
- Provide the authenticated admin monitoring snapshot.

### LuxNix

- Generate the immutable monitored service and storage inventory.
- Provide absolute executable paths, thresholds, service isolation, and collection wiring.
- Provision scrape targets, recording rules, alerts, and dashboards after the metric contract is packaged.

### Operator

- Approve remote scrape exposure, retention, alert routes, and production rollout.

## Host contract

**Environment variable:** `LX_ANNOTATE_MONITORING_CONFIG_FILE`

**Schema version:** 1

**Installed path:** `/etc/lx-annotate/monitoring.json`

**Browser supplied paths or units:** prohibited

**Privilege escalation:** prohibited

**Inaccessible systemd metadata:** unknown

### Defaults

**Systemctl timeout seconds:** 3

**Disk warning free percent:** 10

**Disk error free percent:** 5

**Pending warning seconds:** 3600

**Recent failure window seconds:** 86400

### Validation bounds

**Deployment revision:** `null_or_lowercase_hex_7_to_64`

#### Systemctl timeout seconds

- 1
- 5

#### Pending warning seconds

- 60
- 604800

#### Recent failure window seconds

- 60
- 604800

**Service alias:** `lowercase_letters_digits_underscore_dot_dash_max_64`

**Maximum services:** 40

**Maximum storage paths:** 24

**Aliases unique within each collection:** `true`

## Timing contract

### Clocks

**Execution duration:** monotonic

**Cross process queue wait:** `planned_utc_timestamp_with_skew_detection`

**Event:** `workload.timing`

**Metric:** `workload_duration_seconds`

### Instrumented operations

- `pipeline_ingest`
- `video_import`
- `report_import`
- `hls_materialization`
- `frame_full_materialization`
- `frame_range_materialization`
- `celery_task`

### Phases

- total
- `source_materialization`
- `source_validation`
- `encoder_preflight`
- encode
- decode
- `output_validation`
- publication
- `database_state`
- unknown

### Outcomes

- completed
- failed
- retry
- deferred
- reused
- `validation_failed`
- revoked
- unknown

### Allowed labels

- operation
- `task_family`
- phase
- outcome
- queue
- `retry_bucket`

### Prohibited labels

- `video_id`
- `upload_job_id`
- `task_id`
- filename
- path
- hash
- `exception_message`
- user
- center
- `clinical_value`

## Collection

**Current stage:** `contract_and_host_inventory`

### Current log metric

**Event:** `workload.timing`

**Metric name:** `workload_duration_seconds`

**Unit:** seconds

**Transport:** `structured_application_log`

### Planned metrics

- `lx_annotate_task_duration_seconds`
- `lx_annotate_task_queue_wait_seconds`
- `lx_annotate_task_completed_total`
- `lx_annotate_task_active`
- `lx_annotate_queue_depth`
- `lx_annotate_workflow_phase_duration_seconds`
- `lx_annotate_telemetry_last_success_unixtime`

### Infrastructure signals

- `systemd_unit_state`
- `worker_cpu_throttled_seconds`
- `worker_memory_bytes`
- `worker_io_bytes`
- `nvidia_encoder_utilization`
- `nvidia_gpu_memory_bytes`
- `protected_storage_free_bytes`

**Note:** Prometheus scrape exposure remains disabled until the packaged application metric names and labels pass privacy, cardinality, restart, and stale-data tests.

## Alerts

### Planned

- `stuck_task`
- `queue_growth`
- `sustained_cpu_throttling`
- `hls_encoder_failure`
- `worker_unavailable`
- `protected_storage_pressure`
- `telemetry_stale`

## Rollout

**Deployed:** `false`

**Canary:** gc-10

### Prerequisites

- Package the application timing and admin snapshot contracts in the selected wheel.
- Evaluate and build the gc-10 LuxNix generation without activation.
- Review all labels for privacy and bounded cardinality.
- Exercise synthetic success, failure, retry, deferred, cancellation, and stale cases.

### Rollback

- Disable runtime.monitoring and revert the scrape target without changing application data.
- Preserve structured logs needed for incident analysis according to approved retention.
