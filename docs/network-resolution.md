# Network Resolution

LuxNix generates `/etc/hosts` entries from `luxnix.generic-settings.network.hosts`.

This is useful for stable internal names such as `s-02` or `s-02.intern`, but it must not override public service domains such as `keycloak.endo-reg.net`.

## Why `ping` and `dig` Can Disagree

`ping`, `curl`, browsers, and most applications use NSS resolution. On NixOS this normally checks `/etc/hosts` before DNS.

`dig` and `nslookup` query DNS directly and do not use `/etc/hosts`.

So this output means `/etc/hosts` is overriding DNS:

```text
$ ping -c 4 keycloak.endo-reg.net
PING s-02 (172.16.255.12) ...

$ dig keycloak.endo-reg.net
keycloak.endo-reg.net. 60 IN A 178.104.136.182
```

In that case, application traffic goes to `172.16.255.12`, not to the public DNS address `178.104.136.182`.

## Current Rule

The network module still maps internal hostnames to VPN/private IPs:

```nix
networking.hosts."172.16.255.12" = [
  "s-02"
  "s-02.intern"
];
```

Public DNS names are filtered out of generated `/etc/hosts` by:

```nix
luxnix.generic-settings.network.publicDnsDomains = [
  "adminKeycloak.endo-reg.net"
  "cloud.endo-reg.net"
  "keycloak-admin.endo-reg.net"
  "keycloak.endo-reg.net"
  "nginx.endo-reg.net"
];
```

This prevents `keycloak.endo-reg.net`, `cloud.endo-reg.net`, and `nginx.endo-reg.net` from being pinned to `172.16.255.12` in generated host files.

## Local-Only Domains

Some names are intentionally local aliases. For example:

```nix
luxnix.generic-settings.network.localOnlyDomains = [ "lx-annotate.local" ];
```

`localOnlyDomains` entries are only emitted for the current host. This avoids multiple hosts claiming the same local alias.

## Service-Specific Local Overrides

If a service host needs a public name to resolve to localhost for internal callbacks, define that override in the service module or host config, not in the global generated host inventory.

Example pattern:

```nix
networking.hosts."127.0.0.1" = [
  "cloud.endo-reg.net"
];
```

Use this only on the host that owns the service. Do not apply it globally.

## Verification

After rebuilding:

```bash
sudo nixos-rebuild switch --flake /home/admin/luxnix#<host>
```

Check NSS resolution:

```bash
getent hosts keycloak.endo-reg.net
ping -c 1 keycloak.endo-reg.net
```

Check DNS directly:

```bash
dig keycloak.endo-reg.net
nslookup keycloak.endo-reg.net
```

Expected result:

- `dig` and `nslookup` return the public DNS record.
- `getent hosts keycloak.endo-reg.net` should not return `172.16.255.12` from generated `/etc/hosts`.
- `getent hosts s-02` and `getent hosts s-02.intern` may still return `172.16.255.12`.
