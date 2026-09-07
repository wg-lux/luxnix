# gs-02 Local Redis Broker Recovery

Status: implemented, not deployed. Scope: `gs-02` only.

This runbook replaces the unreachable external Celery broker at
`redis://172.16.255.14:6380/1` with the LX-Annotate module's host-local Redis
instance at `redis://localhost:6379/1`. Activation requires explicit operator
approval and the full preflight below.

## Incident findings

Hub-transfer attempt 21 on 2026-08-28 reached `gs-02` through mTLS, but Nginx
returned 502 because LX-Annotate was not listening on `127.0.0.1:8117`. The web
service remained stopped after its required `lx-annotate-hls-backfill`
dependency rejected Celery dispatch because loopback Redis transport had not
been confirmed. Hub policy, mTLS, and large-video upload were not the cause;
registration never reached the application. `lx-annotate-migrate.service` had
completed successfully at 14:00:31 with no migrations to apply.

## Security decision

- Bind Redis only to `127.0.0.1:6379`; do not open a firewall port.
- Do not use a Redis password while it remains loopback-only. Never expose this
  endpoint to another node.
- Keep Redis volatile: disable RDB and AOF and use `/run/redis-lx-annotate`.
  `gs-02` does not yet have a verified encrypted filesystem boundary for Redis
  persistence.
- Accept that queued messages do not survive a Redis or host restart.
  Database-backed job records remain authoritative and must be reconciled.
- Never bind Redis to `0.0.0.0` or `172.16.255.22`, point `gc-*` or `gs-01` at
  this plaintext endpoint, claim secure node-to-node `redis://` transport, or
  enable persistence outside a verified encrypted mount.

The authoritative change belongs in
`ansible/inventory/host_vars/gs-02.yml`. Do not hand-edit
`autoconf/merged_vars/gs-02.yml` or
`systems/x86_64-linux/gs-02/default.nix`. The intended `host_services` values
are:

```yaml
luxnix.lxAnnotateLocal.runtime.externalServices.redisUrl: null
luxnix.lxAnnotateLocal.runtime.celeryBroker.secureTransportConfirmed: lib.mkForce true
redis.servers."lx-annotate".appendOnly: lib.mkForce false
redis.servers."lx-annotate".save: lib.mkForce [ ]
redis.servers."lx-annotate".settings.dir: lib.mkForce "/run/redis-lx-annotate"
```

Expected evaluation: the Celery URL is `redis://localhost:6379/1`, secure
transport confirmation is true only because the plaintext broker is
loopback-only, `redis-lx-annotate.service` binds `127.0.0.1:6379`, the firewall
remains closed, persistence is disabled, and LX-Annotate workers order after
and want the Redis unit.

## Large-video HTTP transport boundary

The related typed transfer controls live in
`modules/nixos/services/lx-annotate-local/options.nix` and `config.nix`. They
allow at most 53,687,091,200 bytes and use a 21,600-second inactivity timeout.
The dedicated transfer location must use HTTP/1.1 upstream, stream request
bodies, disable response buffering, apply the typed size and timeout controls,
preserve client-certificate verification, and replace any incoming mTLS
attestation header.

## Preflight

Record and review the source before activation:

```bash
git status --short
git rev-parse HEAD
git rev-parse HEAD:flake.lock
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
nix eval '.#nixosConfigurations.gs-02.config.services.luxnix.lxAnnotateLocal.runtime.externalServices.redisUrl'
nix eval '.#nixosConfigurations.gs-02.config.services.redis.servers."lx-annotate"'
nix eval '.#nixosConfigurations.gs-02.config.systemd.services.redis-lx-annotate.after'
nix build '.#nixosConfigurations.gs-02.config.system.build.toplevel' --no-link
```

Confirm that the generated diff is limited to the intended `gs-02` broker
topology, no unrelated dirty changes are included, and the LuxNix revision,
`flake.lock` revision, target, and built closure are recorded.

Previous implementation checks passed Autoconf validation and generation,
focused Redis/large-transfer evaluation, Nix formatting, 37 application
hub-export and wheel-deployment tests, Ruff checks, and whitespace checks. The
full host build remains required: an earlier attempt exhausted the encrypted
root filesystem while fetching an unrelated Triton/CUDA closure after the
Redis, Nginx, runtime-environment, and Celery unit derivations had built. Do not
deploy until authorized recoverable Nix-store cleanup or additional build
space allows the full build to pass.

## Activation

After explicit operator approval:

```bash
sudo nixos-rebuild switch --flake .#gs-02
```

The old `s-04` queue is unavailable and is not migrated by this change.
Preserve database job state and reconcile incomplete jobs after activation.
Never mark jobs complete merely because the new broker starts empty.

## Acceptance

Run:

```bash
sudo systemctl is-active redis-lx-annotate.service
redis-cli -h 127.0.0.1 -p 6379 PING
sudo grep '^CELERY_BROKER_URL=' /var/lib/lx-annotate/.env.systemd
sudo grep '^CELERY_BROKER_SECURE_TRANSPORT_CONFIRMED=' /var/lib/lx-annotate/.env.systemd
sudo systemctl show lx-annotate.service -p Environment
sudo systemctl status 'lx-annotate-celery-*.service' --no-pager
sudo journalctl --namespace=lx-annotate --since '-10 minutes' --no-pager
sudo ss -ltnp 'sport = :6379'
```

Require `PONG`, the intended broker URL and loopback security confirmation,
loopback-only listening, connected workers without retry loops, `appendonly=no`,
no save schedule, and an explicit reconciliation of pending database jobs.
Preserve ambiguous jobs or mark them `LOST` where supported.

## Rollback and recovery

Switch to the previous reviewed NixOS generation. Verify the active generation
and service environment after rollback, and retain database job records and
logs for manual reconciliation. Rollback restores the unreachable `s-04`
broker URL; it cannot recover messages formerly held by `s-04` or messages lost
from the volatile local broker.

## Durable encrypted-mount follow-up

First provision and verify a LUKS/dm-crypt-backed filesystem on `gs-02`, keeping
its key local or delivering it through the existing Vault-managed encrypted
data contract. Only then move Redis data into that mount, enable
`appendOnly=true` with `appendFsync=everysec`, require the mount from
`redis-lx-annotate.service`, and add a Nix assertion rejecting persistent hub
Redis outside a verified storage boundary.

A shared multi-host broker is a separate design. It requires `rediss://`,
authentication, certificate lifecycle management, and scoped firewall rules.
