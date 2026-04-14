# Migration Plan: Home Servers → Hetzner Cloud

## Goal

Migrate critical services from s-01/s-02/s-03 (home LAN behind FritzBox) to Hetzner h-01.
Services: OpenVPN, nginx/reverse-proxy, Keycloak, Nextcloud.

---

## Current state

| # | Phase | Status |
|---|---|---|
| 1 | OpenVPN on h-01 | **Ready to deploy** |
| 2 | Keycloak + nginx + postgres on h-01 | Config done — pending data migration |
| 3 | Firewall hardening | ✅ Done |
| 4 | nginx security improvements | Queued |
| 5 | Nextcloud routing via h-01 nginx | Queued |
| 6 | Decommission s-01/s-02 service roles | After phases 1–2 stable for 1 week |

### h-01 vault deploy — all secrets staged (30 files)

```
~/.lxv/deploy/h-01/
  ssl_cert / ssl_key                          ✅ staged
  SCRT_local_password_admin_password          ✅ staged
  SCRT_local_password_maintenance_password    ✅ staged
  SCRT_roles_system_password_keycloak_*       ✅ staged
  SCRT_groups_system_password_* (22 files)    ✅ staged
```

### master-vault — all certs present

```
master-vault/certificates/
  ssl/endo-reg.net/fullchain.pem + privkey.pem    ✅
  openvpn/ca/ca.pem + ca.key                      ✅
  openvpn/server/crt.crt + key.key + dh.pem       ✅
  openvpn/tls.pem                                  ✅
  openvpn/ccd/  (24 clients)                       ✅
```

### SSH keys — wired through pipeline

Admin key (`IM7vvbg...`) is deployed at `~/.ssh/id_ed25519` and set as `rootIdED25519` in
all generated NixOS configs via `group_luxnix` in `all.yml`. Dev keys are wired via
`group_roles`. See [SSH key reference](#ssh-key-reference) below.

---

## Architecture

### Before (home, behind FritzBox)

```
Internet
   │
FritzBox (dynamic IP, NAT/port-forward)
   ├── :80/:443  → s-02  (192.168.179.2 / VPN 172.16.255.12)  nginx + keycloak + postgres
   ├── :1194     → s-01  (192.168.179.1 / VPN 172.16.255.1)   OpenVPN server
   └── s-03  (192.168.179.3 / VPN 172.16.255.13)              nextcloud + MinIO
```

### After (Hetzner h-01, direct public IP)

```
Internet
   │  static IP 178.104.136.182
   │
h-01 (Hetzner)
   ├── :80/:443     nginx  ──▶  keycloak (tun0 172.16.255.1:8443)
   ├── :1194 TCP    OpenVPN server  ──▶  VPN subnet 172.16.255.0/24
   │                                          ├── s-03 (172.16.255.13, nextcloud) ← phase 5
   │                                          └── gc-*, gs-*, s-04, ...
   └── postgres (5432, tun0 only)
       keycloak (8443, tun0 only)
```

Key differences: static public IP; NixOS firewall IS the firewall (no NAT layer); keycloak
and postgres locked to tun0; nginx and keycloak colocated on h-01.

---

## Phase 1 — OpenVPN cutover

> **Lockout risk.** All NixOS VPN clients use `vpn.endo-reg.net` (hardcoded DNS name). If h-01
> VPN is broken when DNS switches, all remote-only machines (gs-*, gc-*, s-03, s-04) become
> unreachable simultaneously. Follow the sequence below to avoid this.

### Step 0 — One-time: stage the Keycloak admin password

> **Do this once before the first deploy.** The password is stored on the
> master-vault stick and deployed as an ansible-vault encrypted secret file.
> It is never written to the Nix store or any world-readable path.

```bash
# Option A — single task (inside devenv shell):
devenv tasks run secrets:stage-keycloak-admin
# (prints the generated password once — save it in your password manager)

# Option B — step by step (inside devenv shell):
lx-secrets --stick /home/admin/master-vault user set-password --username keycloak_admin --generate
lx-secrets --stick /home/admin/master-vault vault stage-keycloak-admin --hostname h-01

# Verify it's present and vault-encrypted:
lx-secrets vault status h-01
# → SCRT_roles_system_password_keycloak_host_admin_initial_password  [vault-encrypted]
```

At runtime `keycloak-prepare-admin-env.service` reads
`/etc/secrets/vault/SCRT_roles_system_password_keycloak_host_admin_initial_password`
and writes it as `KC_BOOTSTRAP_ADMIN_PASSWORD` into `/run/keycloak-admin-env`
(mode 0600, root-owned). Keycloak picks it up via `EnvironmentFile` on first start,
then ignores it on subsequent boots (it's stored in Keycloak's own DB after that).

### Step 1 — Deploy secrets and NixOS config to h-01

```bash
# Deploy all vault secrets (passwords + SSL cert + keycloak admin password)
ansible-playbook ansible/playbooks/deploy_secrets.yml --limit h-01

# Stage OpenVPN certs locally from the master-vault stick (inside devenv shell)
lx-secrets --stick /home/admin/master-vault cert deploy-openvpn --dest /tmp/vpn-stage

# Copy OpenVPN certs to h-01 (not managed by vault — deployed directly)
rsync -av -e "ssh -i ~/.ssh/ssh-hetzner-main_openssh" \
    /tmp/vpn-stage/ admin@178.104.136.182:/tmp/vpn-stage/
ssh -i ~/.ssh/ssh-hetzner-main_openssh admin@178.104.136.182 \
    'sudo cp /tmp/vpn-stage/*.pem /tmp/vpn-stage/*.crt /tmp/vpn-stage/*.key /etc/openvpn/ && \
     sudo chmod 600 /etc/openvpn/*.pem /etc/openvpn/*.crt /etc/openvpn/*.key && \
     sudo chown root:root /etc/openvpn/*.pem /etc/openvpn/*.crt /etc/openvpn/*.key && \
     sudo mkdir -p /etc/openvpn/ccd && \
     sudo cp -r /tmp/vpn-stage/ccd/* /etc/openvpn/ccd/ && \
     sudo chmod 644 /etc/openvpn/ccd/* && \
     rm -rf /tmp/vpn-stage'
rm -rf /tmp/vpn-stage

# Deploy NixOS config — do NOT change DNS yet
nixos-rebuild switch --flake ".#h-01" --target-host root@178.104.136.182

# Verify VPN server is running
ssh root@178.104.136.182 systemctl status openvpn-aglnet.service
```

s-01 still runs the VPN server. All clients remain connected to s-01.

### Step 2 — Test h-01 VPN from a machine with non-VPN access

```bash
# On a machine reachable without VPN (local workstation or laptop):
sudo openvpn --config /etc/openvpn/aglnet.conf \
  --remote 178.104.136.182 1194 \
  --daemon test-h01

ping 172.16.255.1
curl -sk https://172.16.255.1:8443/realms/master | jq .realm
sudo killall openvpn
```

Do not proceed to Step 3 unless this succeeds cleanly.

### Step 3 — Switch `vpn.endo-reg.net` DNS to h-01

```
vpn.endo-reg.net  A  178.104.136.182
```

New connections go to h-01. Existing s-01 TCP sessions survive the DNS change, so
remote-only machines remain reachable via their still-active s-01 connection.

### Step 4 — Roll over gc-* clients to h-01

Servers (s-*, gs-*) have direct SSH and are unaffected by VPN. Only gc-* machines are
VPN-only. Roll them one at a time via their still-active s-01 session:

```bash
devenv run vpn-client-rollout
```

See [scripts/migration/vpn-client-rollout.sh](scripts/migration/vpn-client-rollout.sh).
The script verifies each client reconnects to h-01 before proceeding to the next.

### Step 5 — Stop s-01 VPN server

```bash
ssh admin@172.16.255.1 sudo systemctl stop openvpn-aglnet.service
```

Leave s-01's server role in NixOS config until Phase 6 (after 1 week stable on h-01).

---

## Phase 2 — Keycloak + nginx + postgres

> **Do not skip the data migration.** Deploying h-01 without migrating data produces a blank
> Keycloak — every application that uses SSO will break immediately.

### Pre-deploy check

All required secrets are staged. Verify before running:

```bash
ls ~/.lxv/deploy/h-01/ | grep -E "ssl_cert|ssl_key|keycloak|admin_password"
```

### ⚠️ Set Keycloak initial admin password before first deploy

`keycloakHost.adminInitialPassword` defaults to `"admin"`. Override it in
`ansible/inventory/host_vars/h-01.yml` before the first deploy:

```yaml
host_roles:
  keycloakHost.adminInitialPassword: "{{ vault_keycloak_admin_password }}"
```

### Deploy + data migration (automated)

Stops s-02 Keycloak, exports realm JSON + pg_dump, deploys h-01, restores, verifies.
Local timestamped pg_dump and realm JSON are saved as rollback artefacts.

```bash
devenv run migrate-keycloak
# If h-01 is already deployed:
devenv run migrate-keycloak -- --skip-deploy
```

See [scripts/migration/keycloak-migrate.sh](scripts/migration/keycloak-migrate.sh).

### Verify services on h-01

```bash
ssh root@178.104.136.182 systemctl status openvpn-aglnet postgresql keycloak nginx

# keycloak must NOT be reachable on public eth0:
curl -v --max-time 5 https://178.104.136.182:8443/   # → connection refused

# keycloak IS reachable through nginx:
curl -v https://keycloak.endo-reg.net/realms/master
```

### DNS cutover

Lower TTL to 300 a few hours before switching.

```
keycloak.endo-reg.net       A  178.104.136.182
adminKeycloak.endo-reg.net  A  178.104.136.182
```

### Rollback

Keep s-02 Keycloak stopped (not decommissioned) for at least 48 hours after cutover.

```bash
# 1. Revert DNS to s-02 (FritzBox external IP / DynDNS) — propagates in ~5 min at TTL 300
# 2. Restart Keycloak on s-02:
ssh admin@s-02 sudo systemctl start keycloak.service
# 3. Verify:
curl -s https://keycloak.endo-reg.net/realms/master | jq .realm
```

Data written to h-01 between cutover and rollback will be lost — announce maintenance window.

---

## Phase 3 — Firewall hardening ✅ Done

Keycloak (8443) and postgres (5432) are bound to `interfaces.tun0` only. Keycloak systemd
dependency uses the correct lowercase service name `openvpn-aglnet.service`.

---

## Phase 4 — nginx security improvements

### 4a. Rate limiting on keycloak login endpoint

In [modules/nixos/roles/nginx-host/default.nix](modules/nixos/roles/nginx-host/default.nix):

```nix
services.nginx.commonHttpConfig = ''
  limit_req_zone $binary_remote_addr zone=keycloak_auth:10m rate=10r/m;
'';
```

In the keycloak virtualHost location `extraConfig`:
```
limit_req zone=keycloak_auth burst=20 nodelay;
limit_req_status 429;
```

### 4b. Security headers

Add to `appendHttpConfig`:

```nix
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
```

### 4c. Backend TLS verification

nginx proxies to `https://172.16.255.1:8443` but the keycloak cert is issued for the domain,
not the IP. Short-term fix in the keycloak virtualHost location:

```nix
proxy_ssl_verify off;
```

### 4d. Fail2ban

```nix
services.fail2ban.enable = true;
```

---

## Phase 5 — Nextcloud routing via h-01 nginx

Nextcloud stays on s-03 (VPN IP 172.16.255.13). nginx on h-01 proxies `cloud.endo-reg.net`
to it. `serviceHosts.nextcloud = "s-03"` is already set; s-03 already trusts h-01 as proxy.

**Enable in `host_vars/h-01.yml`:**

```yaml
host_roles:
  nginxHost.nextcloud.enable: "true"
```

Run autoconf + deploy. Then update DNS:

```
cloud.endo-reg.net  A  178.104.136.182
```

### Future: full Nextcloud migration to cloud (optional)

Multi-hour maintenance window. Script handles maintenance mode, pg_dump, rsync, MinIO mirror,
pg_restore, occ housekeeping, and verification:

```bash
devenv run migrate-nextcloud -- <new-host-ip>
```

See [scripts/migration/nextcloud-migrate.sh](scripts/migration/nextcloud-migrate.sh).
After migration update `serviceHosts.nextcloud` in `all.yml` and DNS.

---

## Phase 6 — Decommission home service roles

Run after phases 1–2 have been stable for at least 1 week.

### s-01: remove VPN server role

```yaml
# host_vars/s-01.yml
host_roles:
  aglnet.host.enable: "false"
  aglnet.client.enable: "true"
```

Remove `ip_vpn = "172.16.255.1"` from the s-01 network hosts block in `all.yml` (it gets
a client IP from the pool). Clean up the duplicate `ip_vpn` entry once s-01 is demoted.

### s-02: remove service roles

```yaml
# host_vars/s-02.yml
host_roles:
  keycloakHost.enable: "false"
  nginxHost.enable: "false"
  postgres.main.enable: "false"
```

Run autoconf and deploy to s-02. Remove s-02 domain entries from `all.yml` network hosts.

---

## SSH key reference

| Identity | Private key | NixOS option | Scope |
|---|---|---|---|
| `admin` | `master-vault/identities/users/admin/id_ed25519` | `generic-settings.rootIdED25519` | All hosts via `common` / `base-server` roles |
| `dev_01` | `master-vault/identities/users/dev_01/id_ed25519` | `roles.ssh-access.dev-01.idEd25519` | Per-host when `enable = true` |
| `dev_03` | `master-vault/identities/users/dev_03/id_ed25519` | `roles.ssh-access.dev-03.idEd25519` | Per-host when `enable = true` |

Public keys are managed in `ansible/inventory/group_vars/stick_pubkeys.yml` (auto-generated).
Values are wired into `group_luxnix` / `group_roles` in `all.yml` and flow through autoconf
into every generated `systems/*/default.nix`.

**To rotate a key:**

```bash
python3 scripts/lx-secrets.py --stick /home/admin/master-vault identity import-keypair <user> \
    --private <new-key> --force
python3 scripts/lx-secrets.py --stick /home/admin/master-vault identity sync-inventory
# Update group_luxnix.generic-settings.rootIdED25519 in all.yml if rotating admin key
python3 scripts/autoconf-pipeline.py
```

---

## Remote Install h-01 (initial bootstrap only)

After a fresh nixos-anywhere install the host reboots into the full NixOS config.
The `hetzner` role now enables `systemd-resolved` + sets NetworkManager to use it,
which fixes DNS on Hetzner cloud VMs. Before this fix, DNS resolved nothing after
first boot (`Could not resolve host: github.com`).

```bash
HOST_PROFILE=h-01 TARGET_HOST=root@178.104.136.182 KEY_FILE=~/.ssh/ssh-hetzner-main_openssh \
  REFRESH_HOST_KEY=true ./scripts/hetzner-remote-install.sh
```

After install completes: run Step 0 and Step 1 above before doing `nixos-rebuild switch`.

---

## Open issues (non-blocking)

| File | Issue |
|---|---|
| `aglnet/client/default.nix:226` | `pull-filter accept "route 172.16.255.12"` — stale client filter for old s-02 route; harmless, clean up post-migration |
| `nginx-host/default.nix:7` | `vpnIp` let-binding defined but unused — dead code |
| `keycloak_host/default.nix:290` | `hostname-admin` setting commented out — admin console may not resolve via the admin domain |
| `generic-settings/default.nix:58` | `vpnIp` default is `"172.16.255.x"` (invalid) — hosts without explicit vpnIp will misconfigure keycloak/postgres bind addresses |

---

## Port and IP reference

| Host | Public IP | VPN IP | Role |
|---|---|---|---|
| h-01 | 178.104.136.182 | 172.16.255.1 (tun0) | VPN server, nginx, keycloak, postgres |
| s-01 | behind FritzBox | 172.16.255.1 → retire | VPN server → Phase 6 |
| s-02 | behind FritzBox | 172.16.255.12 → retire | nginx/keycloak/postgres → Phase 6 |
| s-03 | behind FritzBox | 172.16.255.13 | nextcloud (stays) |

| Port | Exposed on | Service |
|---|---|---|
| 80 | eth0 (public) | nginx HTTP → HTTPS redirect |
| 443 | eth0 (public) | nginx HTTPS |
| 1194 | eth0 (public) | OpenVPN |
| 8443 | tun0 only | keycloak HTTPS |
| 5432 | tun0 only | postgres |
| 53 | tun0 only | dnsmasq (VPN DNS) |
| 9000 | localhost only | MinIO on s-03 |
