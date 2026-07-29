# lx-annotate diagnostics

Run these commands on the target NixOS host. Most commands need `sudo` because
the service runtime, journals, and protected data directories are not world
readable.

The main service is `lx-annotate.service`. It also has the compatibility alias
`lx-annotate-boot.service`.

## Quick overview

```bash
sudo systemctl status lx-annotate.service
sudo systemctl status lx-annotate-boot.service
sudo systemctl list-units 'lx-annotate*'
sudo systemctl list-units 'lx-annotate*' --all
sudo systemctl list-timers 'lx-annotate*' --all
sudo systemctl list-dependencies lx-annotate.service
sudo systemctl list-dependencies --reverse lx-annotate.service
sudo systemctl is-active lx-annotate.service nginx.service redis-lx-annotate.service postgresql.service
sudo systemctl is-failed 'lx-annotate*'
```

Continuous watch:

```bash
watch -n 2 "systemctl --no-pager --plain status lx-annotate.service lx-annotate-celery-worker.service lx-annotate-celery-pipeline-worker.service lx-annotate-celery-ffmpeg-worker.service"
watch -n 5 "systemctl --no-pager --plain list-units 'lx-annotate*'"
watch -n 10 "systemctl --no-pager --plain list-timers 'lx-annotate*' --all"
```

## Logs

```bash
sudo journalctl -u lx-annotate.service -n 200 --no-pager
sudo journalctl -u lx-annotate.service -f
sudo journalctl -u lx-annotate.service --since '1 hour ago'
sudo journalctl -u lx-annotate.service --since today --no-pager
sudo journalctl -u lx-annotate.service -p warning..alert --since '24 hours ago' --no-pager
sudo journalctl -u 'lx-annotate*' --since '1 hour ago' --no-pager
sudo journalctl -u 'lx-annotate*' -p warning..alert --since '24 hours ago' --no-pager
```

Follow the application, nginx, Redis, and PostgreSQL together:

```bash
sudo journalctl -f \
  -u lx-annotate.service \
  -u nginx.service \
  -u redis-lx-annotate.service \
  -u postgresql.service
```

Boot-scoped logs:

```bash
sudo journalctl -b -u lx-annotate.service --no-pager
sudo journalctl -b -u 'lx-annotate*' --no-pager
sudo journalctl -b -u nginx.service -u redis-lx-annotate.service -u postgresql.service --no-pager
```

## Startup chain

The startup-critical LX-Annotate units log to the `lx-annotate` journal
namespace. Read it as a single boot-ordered stream to find the first unit that
failed or delayed startup:

```bash
sudo journalctl --namespace=lx-annotate -b --no-pager
sudo journalctl --namespace=lx-annotate -b -p warning..alert --no-pager
sudo journalctl --namespace=lx-annotate -f
```

```bash
sudo systemctl status lx-annotate-runtime-env.service
sudo systemctl status lx-annotate-migrate.service
sudo systemctl status lx-annotate-load-base-data.service
sudo systemctl status lx-annotate-master-key-check.service
sudo systemctl status lx-annotate.service
```

```bash
sudo journalctl -u lx-annotate-runtime-env.service -n 200 --no-pager
sudo journalctl -u lx-annotate-migrate.service -n 200 --no-pager
sudo journalctl -u lx-annotate-load-base-data.service -n 200 --no-pager
sudo journalctl -u lx-annotate-master-key-check.service -n 200 --no-pager
```

Manually rerun one-shot checks:

```bash
sudo systemctl start lx-annotate-runtime-env.service
sudo systemctl start lx-annotate-migrate.service
sudo systemctl start lx-annotate-load-base-data.service
sudo systemctl start lx-annotate-master-key-check.service
sudo systemctl start lx-annotate-acceptance.service
sudo journalctl -u lx-annotate-acceptance.service -n 200 --no-pager
```

## Web and nginx

Default local Django port: `8117`. Default public vhost: `lx-annotate.local`.

```bash
sudo systemctl status nginx.service lx-annotate.service
sudo nginx -t
sudo journalctl -u nginx.service -n 200 --no-pager
sudo journalctl -u nginx.service -f
ss -ltnp | grep -E ':(443|80|8117)\b'
curl --fail --silent --show-error http://127.0.0.1:8117/ >/dev/null
curl --fail --silent --show-error --cacert /run/lx-annotate-ssl/lx-annotate-selfsigned.crt --resolve lx-annotate.local:443:127.0.0.1 https://lx-annotate.local/ >/dev/null
curl --fail --silent --show-error --cacert /run/lx-annotate-ssl/lx-annotate-selfsigned.crt --resolve lx-annotate.local:443:127.0.0.1 https://lx-annotate.local/static/.vite/manifest.json >/dev/null
```

Inspect nginx's generated vhost:

```bash
sudo nginx -T | sed -n '/server_name lx-annotate.local/,/^[[:space:]]*}/p'
sudo systemctl cat nginx.service
sudo systemctl show nginx.service -p ActiveState -p SubState -p MainPID -p FragmentPath
```

## Celery workers

The service defines these worker units:

- `lx-annotate-celery-worker.service`: `maintenance,default`
- `lx-annotate-celery-pipeline-worker.service`: `pipeline`
- `lx-annotate-celery-frame-extraction-worker.service`: `frame_extraction`
- `lx-annotate-celery-ffmpeg-worker.service`: `ffmpeg_media`
- `lx-annotate-celery-inference-worker.service`: `inference`
- `lx-annotate-celery-training-worker.service`: `model_training`
- `lx-annotate-celery-llm-inference-worker.service`: `llm_inference`

```bash
sudo systemctl status \
  lx-annotate-celery-worker.service \
  lx-annotate-celery-pipeline-worker.service \
  lx-annotate-celery-frame-extraction-worker.service \
  lx-annotate-celery-ffmpeg-worker.service \
  lx-annotate-celery-inference-worker.service \
  lx-annotate-celery-training-worker.service \
  lx-annotate-celery-llm-inference-worker.service
```

```bash
sudo journalctl -u lx-annotate-celery-worker.service -n 200 --no-pager
sudo journalctl -u lx-annotate-celery-pipeline-worker.service -n 200 --no-pager
sudo journalctl -u lx-annotate-celery-frame-extraction-worker.service -n 200 --no-pager
sudo journalctl -u lx-annotate-celery-ffmpeg-worker.service -n 200 --no-pager
sudo journalctl -u lx-annotate-celery-inference-worker.service -n 200 --no-pager
sudo journalctl -u lx-annotate-celery-training-worker.service -n 200 --no-pager
sudo journalctl -u lx-annotate-celery-llm-inference-worker.service -n 200 --no-pager
```

Resource and cgroup monitoring:

```bash
systemd-cgtop
systemd-cgtop /system.slice/lx-annotate.service
sudo systemctl show lx-annotate.service -p MemoryCurrent -p MemoryHigh -p MemoryMax -p CPUUsageNSec -p CPUQuotaPerSecUSec -p TasksCurrent
sudo systemctl show lx-annotate-celery-worker.service -p MemoryCurrent -p MemoryHigh -p MemoryMax -p CPUUsageNSec -p CPUQuotaPerSecUSec -p TasksCurrent
sudo systemctl show lx-annotate-celery-ffmpeg-worker.service -p MemoryCurrent -p MemoryHigh -p MemoryMax -p CPUUsageNSec -p CPUQuotaPerSecUSec -p IOWeight -p TasksCurrent
ps -eo pid,ppid,user,stat,pcpu,pmem,etime,cmd | grep -E 'lx-annotate|celery|uvicorn|gunicorn' | grep -v grep
```

Frame extraction timer mode:

```bash
sudo systemctl status lx-annotate-celery-frame-extraction-worker.timer
sudo systemctl list-timers 'lx-annotate-celery-frame-extraction-worker*' --all
sudo journalctl -u lx-annotate-celery-frame-extraction-worker.timer -n 100 --no-pager
sudo systemctl start lx-annotate-celery-frame-extraction-worker.service
sudo systemctl stop lx-annotate-celery-frame-extraction-worker.service
```

FFmpeg stream throttling, when enabled:

```bash
sudo systemctl status lx-annotate-ffmpeg-stream-throttle.service
sudo systemctl status lx-annotate-ffmpeg-stream-throttle.timer
sudo journalctl -u lx-annotate-ffmpeg-stream-throttle.service -n 200 --no-pager
sudo systemctl start lx-annotate-ffmpeg-stream-throttle.service
sudo cat /run/lx-annotate/ffmpeg-stream-throttle.state
```

## Redis broker

Local Redis is `redis-lx-annotate.service` on `127.0.0.1:6379` unless an
external broker is configured.

```bash
sudo systemctl status redis-lx-annotate.service
sudo journalctl -u redis-lx-annotate.service -n 200 --no-pager
redis-cli -h 127.0.0.1 -p 6379 PING
redis-cli -h 127.0.0.1 -p 6379 INFO server
redis-cli -h 127.0.0.1 -p 6379 INFO persistence
redis-cli -h 127.0.0.1 -p 6379 INFO memory
redis-cli -h 127.0.0.1 -p 6379 INFO clients
redis-cli -h 127.0.0.1 -p 6379 INFO stats
redis-cli -h 127.0.0.1 -p 6379 LLEN default
redis-cli -h 127.0.0.1 -p 6379 LLEN maintenance
redis-cli -h 127.0.0.1 -p 6379 LLEN pipeline
redis-cli -h 127.0.0.1 -p 6379 LLEN frame_extraction
redis-cli -h 127.0.0.1 -p 6379 LLEN ffmpeg_media
redis-cli -h 127.0.0.1 -p 6379 LLEN inference
redis-cli -h 127.0.0.1 -p 6379 LLEN model_training
redis-cli -h 127.0.0.1 -p 6379 LLEN llm_inference
redis-cli -h 127.0.0.1 -p 6379 KEYS '*unacked*'
```

Queue watch:

```bash
watch -n 5 "redis-cli -h 127.0.0.1 -p 6379 LLEN default; redis-cli -h 127.0.0.1 -p 6379 LLEN pipeline; redis-cli -h 127.0.0.1 -p 6379 LLEN frame_extraction; redis-cli -h 127.0.0.1 -p 6379 LLEN ffmpeg_media; redis-cli -h 127.0.0.1 -p 6379 LLEN inference; redis-cli -h 127.0.0.1 -p 6379 LLEN model_training; redis-cli -h 127.0.0.1 -p 6379 LLEN llm_inference"
```

## Celery broker settings warnings

`endoreg_db.W001` is emitted by the Django system check
`endoreg_db.checks.check_celery_runtime_configuration`. It means Django loaded
settings with an empty `settings.CELERY_BROKER_URL` while one or more
Celery-backed job modes are enabled. It is not a systemd warning.

LuxNix exports `CELERY_BROKER_URL` into the generated unit environment and
`/var/lib/lx-annotate/.env.systemd`. If systemd shows the value but Django still
emits `endoreg_db.W001`, inspect the lx-annotate settings module: the setting
must be present as `settings.CELERY_BROKER_URL`, not only in `os.environ`.

```bash
sudo systemctl cat lx-annotate-ffmpeg-stream-throttle.service | grep CELERY_BROKER_URL
sudo grep '^CELERY_BROKER_URL=' /var/lib/lx-annotate/.env.systemd
sudo systemctl show lx-annotate-ffmpeg-stream-throttle.service -p Environment | tr ' ' '\n' | grep CELERY_BROKER_URL
sudo -u endoreg-service-user bash -lc 'set -a; . /var/lib/lx-annotate/.env.systemd; set +a; python - <<'"'"'PY'"'"'
import os
url = os.environ.get("CELERY_BROKER_URL", "")
print(f"env CELERY_BROKER_URL set={bool(url)} scheme={url.split(':', 1)[0] if url else ''}")
PY'
sudo -u endoreg-service-user bash -lc 'set -a; . /var/lib/lx-annotate/.env.systemd; set +a; /var/endoreg-service-user/lx-annotate-wheel/.venv/bin/python - <<'"'"'PY'"'"'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lx_annotate.settings.settings_prod")
import django
django.setup()
from django.conf import settings
url = getattr(settings, "CELERY_BROKER_URL", "")
print(f"settings.CELERY_BROKER_URL set={bool(url)} scheme={url.split(':', 1)[0] if url else ''}")
PY'
```

## PostgreSQL

Default lx-annotate database connection uses local PostgreSQL on port `5433`.

```bash
sudo systemctl status postgresql.service postgres-endoreg-setup.service
sudo journalctl -u postgresql.service -n 200 --no-pager
sudo journalctl -u postgres-endoreg-setup.service -n 200 --no-pager
pg_isready -h 127.0.0.1 -p 5433
sudo -u postgres psql -p 5433 -c '\l'
sudo -u postgres psql -p 5433 -c '\du'
sudo -u postgres psql -p 5433 -d endoregDbLocal -c 'select now();'
sudo -u postgres psql -p 5433 -d endoregDbLocal -c "select pid, usename, application_name, client_addr, state, wait_event_type, wait_event, now() - query_start as age, left(query, 160) as query from pg_stat_activity order by query_start nulls last;"
sudo -u postgres psql -p 5433 -d endoregDbLocal -c "select relname, n_live_tup, n_dead_tup, last_vacuum, last_autovacuum, last_analyze, last_autoanalyze from pg_stat_user_tables order by n_dead_tup desc limit 20;"
```

### Repeated endoreg_db introspection failures

The following critical identifiers mean that Django could not inspect the live
database:

- `lx_annotate.endoreg_db_schema_introspection_failed`
- `lx_annotate.endoreg_db_constraint_introspection_failed`

They do not, by themselves, mean that the installed `endoreg_db` package or its
feature tracker is out of sync. The checker queries each required table and
constraint separately, so one connection or permission problem can produce
many copies of these messages.

LuxNix handles the database boundary through one shared environment contract:

- `scripts/env.nix` renders the selected `database.*` options, including
  `database.sslMode`, into `DJANGO_DB_*`
- `lx-annotate-runtime-env.service` writes those values to
  `/var/lib/lx-annotate/.env.systemd`
- the password remains file-backed in the application configuration directory
- `lx-annotate-migrate.service` runs before base-data loading, the master-key
  check, and the web service
- local PostgreSQL and its setup unit are ordered before application units when
  `runtime.externalServices.postgresHost` is unset

First inspect non-secret connection metadata and confirm that the service user
can read the password file:

```bash
sudo sed -n -E '/^DJANGO_DB_(ENGINE|NAME|USER|HOST|PORT|SSLMODE|PASSWORD_FILE)=/p' \
  /var/lib/lx-annotate/.env.systemd
sudo -u endoreg-service-user bash -c '
  set -a
  . /var/lib/lx-annotate/.env.systemd
  set +a
  test -n "$DJANGO_DB_PASSWORD_FILE"
  test -r "$DJANGO_DB_PASSWORD_FILE"
  test -s "$DJANGO_DB_PASSWORD_FILE"
  printf "database password file is readable and non-empty\n"
'
```

Then find the first failed unit in the ordered startup chain:

```bash
sudo systemctl status \
  postgresql.service \
  postgres-endoreg-setup.service \
  lx-annotate-runtime-env.service \
  lx-annotate-migrate.service \
  lx-annotate-load-base-data.service \
  lx-annotate-master-key-check.service \
  lx-annotate.service
sudo journalctl --namespace=lx-annotate -b -p warning..alert --no-pager
sudo journalctl -u postgresql.service -u postgres-endoreg-setup.service -b --no-pager
sudo journalctl -u lx-annotate-migrate.service -b --no-pager
```

Use the underlying database error from the migration or PostgreSQL journal to
classify the failure:

- `server does not support SSL, but SSL was required`: the configured
  `DJANGO_DB_SSLMODE` does not match the endpoint's TLS capability
- `password authentication failed`: the provisioned database password and the
  application password file disagree
- connection refused or timeout: host, port, listener, firewall, or unit
  ordering is wrong
- permission denied while reading schema metadata or tables: the application
  database role lacks the required query or introspection permissions
- a specific missing-table, missing-column, missing-constraint, or
  constraint-violation identifier: connectivity works and the live schema or
  data is genuinely behind the deployed migration contract

For the module's local PostgreSQL topology, the default SSL mode is `prefer`,
which can connect to the local non-TLS listener. For an external PostgreSQL
host, configure fail-closed TLS and its trust material explicitly; do not use
the fallback behavior of `prefer` across a node-to-node network. The module
exports the chosen mode but does not currently enforce a secure external value.

After correcting environment, TLS, credentials, or permissions, rerun the
ordered gates instead of invoking Django from an unrelated checkout shell:

```bash
sudo systemctl restart lx-annotate-runtime-env.service
sudo systemctl restart lx-annotate-migrate.service
sudo systemctl restart lx-annotate-load-base-data.service
sudo systemctl restart lx-annotate-master-key-check.service
sudo systemctl restart lx-annotate.service
sudo systemctl start lx-annotate-acceptance.service
sudo journalctl -u lx-annotate-acceptance.service -n 200 --no-pager
```

`lx-annotate-acceptance.service` is the final host-level check. The
`endoreg-db/feature-tracking` YAML is release evidence and is not read by these
units; package/revision alignment and the live database gate must be verified
separately.

## Intake and file triggers

```bash
sudo systemctl status lx-annotate-filewatcher.path lx-annotate-filewatcher.service
sudo systemctl status lx-annotate-sap-import.path lx-annotate-sap-import.service
sudo journalctl -u lx-annotate-filewatcher.service -n 200 --no-pager
sudo journalctl -u lx-annotate-sap-import.service -n 200 --no-pager
sudo systemctl start lx-annotate-filewatcher.service
sudo systemctl start lx-annotate-sap-import.service
sudo systemctl show lx-annotate-filewatcher.path -p ActiveState -p SubState -p Triggers -p FragmentPath
sudo systemctl show lx-annotate-sap-import.path -p ActiveState -p SubState -p Triggers -p FragmentPath
```

Default watched paths:

```bash
sudo find /var/lib/lx-annotate/data/import -maxdepth 3 -type d -print
sudo find /var/lib/lx-annotate/data/import/video_import -maxdepth 1 -type f -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort
sudo find /var/lib/lx-annotate/data/import/report_import -maxdepth 1 -type f -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort
sudo find /var/lib/lx-annotate/data/import/preanonymized_import -maxdepth 1 -type f -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort
sudo find /var/lib/lx-annotate/data/import/sap_import -maxdepth 1 -type f -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort
```

If `move-my-files` is enabled:

```bash
sudo systemctl status move-my-files.service
sudo journalctl -u move-my-files.service -n 200 --no-pager
sudo find /var/lib/lx-annotate/data/import/mover-staging -maxdepth 2 -printf '%TY-%Tm-%Td %TH:%TM %m %u:%g %s %p\n' 2>/dev/null | sort
```

## Storage and encrypted data

```bash
sudo systemctl status lx-annotate-encrypted-data.service
sudo journalctl -u lx-annotate-encrypted-data.service -n 200 --no-pager
findmnt /var/lib/lx-annotate/data
findmnt -T /var/lib/lx-annotate/data
df -h /var/lib/lx-annotate /var/lib/lx-annotate/data
sudo du -xh --max-depth=1 /var/lib/lx-annotate/data | sort -h
sudo du -xh --max-depth=1 /var/lib/lx-annotate/data/storage | sort -h
sudo du -xh --max-depth=1 /var/lib/lx-annotate/data/storage/streamable_videos 2>/dev/null | sort -h
sudo find /var/lib/lx-annotate/data -xdev -type f -printf '%s %p\n' | sort -nr | head -50
sudo find /var/lib/lx-annotate/data -xdev -type f -mtime -1 -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' | sort
```

Runtime and wheel installation state:

```bash
sudo ls -la /var/lib/lx-annotate
sudo ls -la /var/lib/lx-annotate/data
sudo ls -la /var/lib/lx-annotate/staticfiles/.vite
sudo cat /var/lib/lx-annotate/.wheel-install.sha256
sudo test -x /var/endoreg-service-user/lx-annotate-wheel/.venv/bin/python && sudo /var/endoreg-service-user/lx-annotate-wheel/.venv/bin/python --version
```

Do not print `/var/lib/lx-annotate/.env.systemd`; it contains sensitive runtime
configuration. Use these instead:

```bash
sudo test -r /var/lib/lx-annotate/.env.systemd && echo readable
sudo stat -c '%A %U:%G %n' /var/lib/lx-annotate/.env.systemd /var/lib/lx-annotate/data/.env.systemd
sudo systemctl show lx-annotate.service -p EnvironmentFiles -p User -p Group -p SupplementaryGroups -p WorkingDirectory
```

## Django checks

The production environment is supplied by systemd. Prefer the acceptance unit
for a faithful check:

```bash
sudo systemctl start lx-annotate-acceptance.service
sudo journalctl -u lx-annotate-acceptance.service -n 200 --no-pager
```

Inspect service command lines and generated unit configuration:

```bash
sudo systemctl cat lx-annotate.service
sudo systemctl cat lx-annotate-migrate.service
sudo systemctl cat lx-annotate-master-key-check.service
sudo systemctl show lx-annotate.service -p ExecStart -p EnvironmentFiles -p WorkingDirectory -p User -p Group -p ReadWritePaths
```

## Manual jobs

```bash
sudo systemctl start lx-annotate-export-frames.service
sudo journalctl -u lx-annotate-export-frames.service -n 200 --no-pager
```

If enabled:

```bash
sudo systemctl status lx-annotate-data-recovery.service
sudo journalctl -u lx-annotate-data-recovery.service -n 200 --no-pager
sudo systemctl status lx-annotate-data-cleanup.service lx-annotate-data-cleanup.timer
sudo journalctl -u lx-annotate-data-cleanup.service -n 200 --no-pager
sudo systemctl status lx-annotate-emergency-storage-relief.service lx-annotate-emergency-storage-relief.timer
sudo journalctl -u lx-annotate-emergency-storage-relief.service -n 200 --no-pager
sudo systemctl status lx-annotate-hub-backup.service lx-annotate-hub-backup.timer
sudo journalctl -u lx-annotate-hub-backup.service -n 200 --no-pager
```

## NixOS evaluation and rebuild checks

From `/home/admin/luxnix`:

```bash
nix flake check
sudo nixos-rebuild dry-run --flake .#$(hostname)
sudo nixos-rebuild switch --flake .#$(hostname)
```

Inspect the evaluated option values for a rebuilt host:

```bash
nixos-option services.luxnix.lxAnnotateLocal.enable
nixos-option services.luxnix.lxAnnotateLocal.django.hostname
nixos-option services.luxnix.lxAnnotateLocal.django.port
nixos-option services.luxnix.lxAnnotateLocal.runtime.mode
nixos-option services.luxnix.lxAnnotateLocal.runtime.encryptedDataDir
nixos-option services.luxnix.lxAnnotateLocal.runtime.externalServices.redisUrl
nixos-option services.luxnix.lxAnnotateLocal.runtime.externalServices.postgresHost
nixos-option services.luxnix.lxAnnotateLocal.runtime.frameExtractionWorker.mode
nixos-option services.luxnix.lxAnnotateLocal.runtime.ffmpegWorker.mode
nixos-option services.luxnix.lxAnnotateLocal.runtime.inferenceWorker.mode
nixos-option services.luxnix.lxAnnotateLocal.runtime.trainingWorker.mode
nixos-option services.luxnix.lxAnnotateLocal.runtime.llmInferenceWorker.mode
```

## Failure triage shortcuts

```bash
sudo systemctl --failed
sudo systemctl reset-failed 'lx-annotate*'
sudo journalctl -p err..alert --since '24 hours ago' --no-pager
sudo journalctl -u 'lx-annotate*' -p err..alert --since '24 hours ago' --no-pager
sudo systemctl show lx-annotate.service -p ActiveState -p SubState -p Result -p ExecMainStatus -p NRestarts -p RestartUSec -p OOMPolicy
sudo systemctl show lx-annotate.service -p MemoryCurrent -p MemoryPeak -p TasksCurrent -p CPUUsageNSec
sudo dmesg -T | grep -Ei 'oom|killed process|lx-annotate|postgres|redis|nginx'
```

Restart order for ordinary application recovery:

```bash
sudo systemctl restart lx-annotate-runtime-env.service
sudo systemctl restart lx-annotate-migrate.service
sudo systemctl restart lx-annotate-load-base-data.service
sudo systemctl restart lx-annotate-master-key-check.service
sudo systemctl restart lx-annotate.service
sudo systemctl restart lx-annotate-celery-worker.service lx-annotate-celery-pipeline-worker.service lx-annotate-celery-ffmpeg-worker.service
```

Full local stack restart:

```bash
sudo systemctl restart redis-lx-annotate.service postgresql.service
sudo systemctl restart lx-annotate.service nginx.service
sudo systemctl restart \
  lx-annotate-celery-worker.service \
  lx-annotate-celery-pipeline-worker.service \
  lx-annotate-celery-ffmpeg-worker.service
```
