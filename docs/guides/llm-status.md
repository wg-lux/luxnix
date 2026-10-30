# GPU server LLM API readiness and sampled availability

**Schema version:** 1

## Scope

### Hosts

- gs-01
- gs-02

**Risk:** remote-read-only

**Collector:** `scripts/llm-status.py`

**Configuration:** `scripts/llm-status.yml`

**Runtime:** Controller-local loopback HTTP server; no remote installation or host activation.

## Commands

### Snapshot

```bash
uv run python scripts/llm-status.py --once
```

### Serve

```bash
uv run python scripts/llm-status.py
```

**Tests:** uv run pytest -q tests/test_llm_status.py

### Controller service status

```bash
systemctl --user status luxnix-llm-status.service
```

### Controller service stop

```bash
systemctl --user stop luxnix-llm-status.service
```

## API

**Listen:** `http://127.0.0.1:8788`

### Endpoints

**`/status`:** HTTP 200 with versioned JSON, individual endpoint states, timestamps, HTTP codes and latency.

**`/uptime`:** Same snapshot including rolling 1-hour, 24-hour and 7-day availability samples.

**`/ready`:** HTTP 200 only when every configured endpoint has a fresh ready response; otherwise 503.

**`/health`:** Collector freshness only; HTTP 503 before samples exist or after sampling becomes stale.

**Unknown routes:** HTTP 404 JSON; URL parameters cannot select probe targets.

**Cache control:** no-store

**Endpoint failure:** Reported in JSON without making the status API itself unavailable.

## Readiness

**Ollama:** HTTP 200 with a nonempty version string; proves API availability, not successful inference.

**Glm:** HTTP 200 with status=ok from llama-server health; a loading model returning 503 is unavailable.

**Authentication:** HTTP 401 or 403 is authentication_required, never proof of backend readiness.

**Redirects:** Not followed; login redirects are reported separately.

**TLS:** Certificate verification remains enabled.

**Stale:** More than two configured intervals plus one probe timeout without a completed sample becomes unknown.

## Availability

**Storage:** `logs/llm-status.sqlite3`

**Permissions:** Database mode 0600; logs are local and Git-ignored.

**Retention days:** 7

**Cadence seconds:** 60

**Interpretation:** Ready samples divided by observed samples; this is sampled availability, not continuous uptime.

**Coverage:** Compare samples with expected_samples and first/last timestamps; gaps are unknown, never assumed healthy.

**History:** Begins when the collector starts; retained across collector restarts, pruned after seven days.

**Host uptime:** Not inferred from endpoint samples or systemd ActiveState.

**Inference:** No automatic generation, training, model downloads, or clinical payloads in probes.

## Operations

- Keep the collector running to accumulate history; foreground execution ends when its process is stopped.
- The listener is loopback-only and does not add firewall rules or bypass public endpoint authentication.
- A durable boot-time deployment is a separate host configuration change; this controller process is not that deployment.

## Current controller run

**Host:** gc-02

**Service:** `luxnix-llm-status.service`

**Kind:** Transient user systemd service with Restart=on-failure and RestartSec=5.

**Source:** `/home/admin/luxnix`

### Start command

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD systemd-run --user --unit=luxnix-llm-status --description='LuxNix LLM endpoint status and availability' --property=Restart=on-failure --property=RestartSec=5 --property=WorkingDirectory=/home/admin/luxnix --property=UMask=0077 /home/admin/luxnix/.devenv/state/venv/bin/python3 /home/admin/luxnix/scripts/llm-status.py --database /home/admin/luxnix/logs/llm-status.sqlite3
```

**Limitation:** Transient service does not install boot-time startup; collection stops when the user manager stops or gc-02 reboots.

**Library environment:** The start command removes inherited library overrides from systemd-run because this shell has a demonstrated glibc mismatch.

### Acceptance

**`/health`:** HTTP 200 with collector_fresh=true.

**`/status`:** HTTP 200 with both hosts and all five configured endpoint observations.

**`/uptime`:** HTTP 200 with persisted sample counts and coverage timestamps.

**`/ready`:** HTTP 503 because configured LLM endpoints are unavailable or authentication-protected.

## Diagnosis 2026 09 09

### `gs-01`

**Ssh:** Verified using the existing gs-01 known-host key against its inventory address.

**Services:** Both ollama.service and glm-5-2.service are not-found in the deployed system.

**Local ollama api:** Connection refused on port 11434.

### `gs-02`

**Glm:** Repeated CUDA allocation failure requesting 223310.60 MiB on a 16376 MiB RTX 4080 SUPER.

**Cause:** Inventory sets gpuLayers=999; llama.cpp logs that automatic fitting is disabled by this explicit value.

**Restart count observed:** 685

**Vpn glm health http:** 503

**Public glm health http:** 403

**Ollama version http:** 200

#### Local inference

**Model:** smollm2:135m

**Http status:** 200

**Response:** Two plus two equals four.

**Total duration seconds:** `1.222`

**Limitation:** Small-model smoke test establishes local inference only, not suitability for clinical tasks.

### Blockers

- The GLM model allocation is about 223 GiB while gs-02 has 16 GiB VRAM and 93 GiB RAM; lowering GPU layers alone does not prove usability.
- gs-02 admin sudo requires a password and root SSH is denied; no privileged remediation was performed.
- The connectivity wrapper exited zero despite a rescued whoami library mismatch; its task output reports error.
- GLM active learning is deferred while API stability and reports take priority; no training loop was enabled.
