# Worker configuration and lifecycle rules

Every Celery worker is declared through the typed `mkWorker` constructor in
[`worker.nix`](worker.nix). It validates a common record and produces the shape
consumed by the service and timer renderers in [`config.nix`](config.nix).
Celery Beat is a separate scheduler and does not use the worker record.

## Ownership and configuration flow

Inventory and Endoreg role settings supply the existing public options under
`services.luxnix.lxAnnotateLocal.runtime`. Their definitions remain in
[`options/runtime.nix`](options/runtime.nix). Host inventory changes still use
the documented Autoconf workflow; do not edit generated host Nix files.

`config.nix` assembles `workerConfigs`, including host-specific dependencies,
environment and scheduling policy. `mkWorker` validates each record, maps its
pool to systemd resource controls, and omits optional fields whose value is
`null`. `mkWorkerService` and `workerTimers` render these normalized records.
The modules under [`subservices/workers/`](subservices/workers/) bind individual
service and timer names.

This is an internal Nix interface. Existing public option paths, unit names,
queues and host defaults remain unchanged. In particular, `runtime.workerLimits`
still overrides the maintenance pool's `memoryHigh`, `memoryMax` and `cpuQuota`.
Secret handling remains file-backed; do not put secret values in worker records.

## Constructor input

Unknown fields, missing required fields and incorrect types fail during Nix
evaluation. The entire record is checked even when a caller reads only one
output field.

| Required field | Shape |
| --- | --- |
| `unitName` | Systemd unit basename without `.service`; letters, digits, underscores and hyphens. |
| `hostname` | Nonempty Celery node prefix; the renderer appends `@%%h`. |
| `queues` | Nonempty, unique list of names containing letters, digits, underscores and hyphens. |
| `pool` | Complete resource record described below. |

| Optional field | Shape | Default |
| --- | --- | --- |
| `mode` | `always`, `manual` or `timer` | `always` |
| `environment` | Attribute set of strings | `{ }` |
| `after`, `wants`, `requires` | Lists of nonempty systemd unit names | `[ ]` |
| `cudaVisibleDevices` | Nonempty string or null | `null` |
| `taskSoftTimeLimitSeconds`, `taskHardTimeLimitSeconds` | Positive integer or null | `null` |
| `onCalendar`, `randomizedDelaySec` | Nonempty string or null | `null` |
| `persistentTimer` | Boolean or null | `null` |
| `runtimeMaxSec`, `timeoutStopSec` | Nonempty string or null | `null` |

Timer mode requires `onCalendar`, `randomizedDelaySec` and `persistentTimer`.
Explicit `persistentTimer = false` is valid. When both task limits are supplied,
the soft limit must be strictly less than the hard limit.

Systemd remains responsible for calendar, duration and resource-string syntax;
the constructor checks that those strings are nonempty. Timer fields may remain
present in other modes so changing a public scheduling mode does not require
removing its timer configuration.

## Resource pool

All fields are required in the internal record. Public `runtime.workerPools`
options supply defaults before the record reaches the constructor.

| Field | Shape | Output |
| --- | --- | --- |
| `concurrency` | Positive integer | Celery `--concurrency` |
| `maxTasksPerChild` | Positive integer | Celery `--max-tasks-per-child` |
| `memoryHigh` | Nonempty string | `serviceConfig.MemoryHigh` |
| `memoryMax` | Nonempty string | `serviceConfig.MemoryMax` |
| `cpuQuota` | Nonempty string | `serviceConfig.CPUQuota` |
| `cpuWeight` | Integer, 1–10000 | `serviceConfig.CPUWeight` |
| `ioWeight` | Integer, 1–10000 | `serviceConfig.IOWeight` |
| `nice` | Integer, -20–19 | `serviceConfig.Nice` |
| `oomScoreAdjust` | Integer, -1000–1000 | `serviceConfig.OOMScoreAdjust` |

## Activation and shutdown

| Internal mode | Automatic activation | Restart policy |
| --- | --- | --- |
| `always` | `multi-user.target` | `on-failure` |
| `manual` | None | `no` |
| `timer` | Calendar timer through `timers.target` | `no` |

Frame extraction translates its public `maintenance-window` mode to `timer`.
Hub transfer and LLM activation retain their existing conditional host policy.
The renderer defaults `TimeoutStopSec` to `45min` when omitted; worker overrides,
including the FFmpeg warm-shutdown timeout, take precedence. A supplied
`runtimeMaxSec` remains effective independently of activation mode.

Shutdown, reboot, and service restart wait for workers to stop. Allow active
LX-Annotate tasks to finish within the configured stop grace period; a long
stop job alone is not evidence of a hung worker. The default is `45min`, frame
extraction defaults to `45min`, and FFmpeg defaults to `6h15min` through
`runtime.ffmpegWorker.timeoutStopSec`. These are bounded waits: systemd may
send a final kill signal after the timeout. They do not guarantee task completion
or an empty broker queue.

Before planned maintenance, pause task submission and scheduling, account for
timer-triggered workers and Celery Beat, and inspect active tasks and worker
logs. Keep required database, broker, and storage services available while
workers finish. Do not shorten stop timeouts or force-kill workers merely to
speed up shutdown. Investigate stalled work and record any explicitly approved
forced interruption and recovery checks.

Use the effective host unit settings when planning downtime; inventory or host
overrides can change these defaults. After restart, verify worker health and
task outcomes before resuming submissions. This repository configures the stop
budget, but application signal handling and successful task recovery require
runtime verification; local Nix evaluation alone does not establish them.

## Existing workers

The unit column omits `.service`; the pool column names `runtime.workerPools` keys.

| Worker | Unit | Celery hostname | Queues | Pool |
| --- | --- | --- | --- | --- |
| maintenance | `lx-annotate-celery-worker` | `maintenance` | `maintenance`, `default` | `maintenance` |
| hub-transfer | `lx-annotate-celery-hub-transfer-worker` | `hub-transfer` | `hub_transfer` | `hubTransfer` |
| pipeline | `lx-annotate-celery-pipeline-worker` | `pipeline` | `pipeline` | `pipeline` |
| frame-extraction | `lx-annotate-celery-frame-extraction-worker` | `frame-extraction` | `frame_extraction` | `frameExtraction` |
| ffmpeg | `lx-annotate-celery-ffmpeg-worker` | `ffmpeg-media` | `ffmpeg_media` | `ffmpeg` |
| inference | `lx-annotate-celery-inference-worker` | `inference` | `inference` | `inference` |
| training | `lx-annotate-celery-training-worker` | `model-training` | `model_training` | `training` |
| llm-inference | `lx-annotate-celery-llm-inference-worker` | `llm-inference` | `llm_inference` | `llmInference` |

## Adding or changing a worker

With `runtime.frontendRequestThrottle.enable`, all Celery pools share
`lx-annotate-background.slice`, including maintenance and hub transfer. File
watching, SAP import, frame export and the external file mover also join this
slice. The controller limits their aggregate CPU and I/O resources during API
requests and the trailing activity window; individual worker limits still apply.
Startup gates remain outside the background slice. Disabling request throttling
removes these LuxNix slice assignments.

The upstream LX-Annotate Nix module additionally defines sibling foreground and
background slices for proportional scheduling. Consume the reviewed upstream
module release to enable that policy; a wheel update alone is insufficient.
Slice changes require service restarts, so preserve the shutdown rules above.
Web CPU quotas and memory limits must still leave enough capacity for annotation.

Use the same record layout as the existing pipeline worker:

```nix
pipeline = mkWorker {
  unitName = "lx-annotate-celery-pipeline-worker";
  hostname = "pipeline";
  queues = [ "pipeline" ];
  pool = cfg.runtime.workerPools.pipeline;
  environment = postValidationWorkerEnv;
};
```

Keep host dependencies and policy in `config.nix`. Introduce a new record field
in the constructor and this document together. Keep queue names aligned with
the application routing contract. Add the corresponding leaf unit and aggregator
entry when introducing a worker.

Run the constructor tests and service evaluation contracts from the repository root:

```bash
uv run pytest -q tests/lx-annotate/test_lx_annotate_worker_shape.py
uv run pytest -q tests/lx-annotate/test_lx_annotate_nix_eval_contract.py
devenv tasks run docs:check
```

Tests should cover invalid records as well as rendered behavior, including
manual and timer modes. Local evaluation does not activate services or establish
runtime readiness.
