# CA Trust and Certificate Repair

LuxNix publishes one system CA bundle for every host and repairs mutable
Python environments that would otherwise keep their own bundled roots.
The module is `modules/nixos/luxnix/ca-trust/` and is enabled fleet-wide by
default (`luxnix.caTrust.enable`).

## Why it exists

CVE-2026-111943 (eMudhra intermediate CA compromise, October 2026) led
Mozilla to distrust `Comodo AAA Services root` and the emSign roots
`emSign ECC Root CA - G3`, `emSign Root CA - C1` and
`emSign ECC Root CA - C3`. Since 2026-10-20, nixpkgs
`nixos/modules/security/ca.nix` on `nixos-26.05` and `nixos-unstable`
appends these labels to the system bundle blacklist. The `cacert` package
itself (NSS 3.126) still ships them until the cacert 3.131.1 update lands.
Mozilla did not distrust `emSign Root CA - G1`, so LuxNix keeps it too.

The upstream fix only changes the NixOS system bundle. Before this module,
LuxNix pointed `SSL_CERT_FILE`, `NIX_SSL_CERT_FILE`, the Nix daemon and the
lx-annotate services at the unfiltered `pkgs.cacert` bundle, and the
lx-annotate wheel venv used `certifi` and pip's vendored copy from PyPI.
All of these bypassed the blacklist. Version bumps of `certifi`, `pip`,
`uv`, `sigstore` or `conda` alone do not fix this on NixOS: nixpkgs
`certifi` reads the `cacert` bundle or `NIX_SSL_CERT_FILE`.

## What the module does

1. Adds `luxnix.caTrust.distrustedCertificates` to
   `security.pki.caCertificateBlacklist`. The default list mirrors the
   upstream labels above. Upstream appends them anyway; listing them here
   puts them under the build check and keeps them distrusted on a nixpkgs
   pin that predates the upstream change.
2. Sets `security.pki.useCompatibleBundle = true`. The default NixOS bundle
   keeps a blacklisted root as an OpenSSL `TRUSTED CERTIFICATE` block marked
   "Rejected for". OpenSSL honours that marker only when the bundle is loaded
   as a file. Python `cadata=`, rustls, Node and other parsers drop the
   marker and would trust the root again. The compatible bundle holds only
   roots trusted for server authentication, plus private CAs from
   `security.pki.certificateFiles`, with no OpenSSL trust rules. Email-only
   and code-signing-only Mozilla roots are therefore not in
   `/etc/ssl/certs/ca-certificates.crt`.
3. Adds a `system.checks` derivation that fails the system build if any
   distrusted certificate (matched by DER content, in either PEM form) is
   still in `config.security.pki.caBundle`. It also fails if a configured
   label no longer exists in the pinned cacert, which means upstream removed
   it and the entry should be deleted.
4. Installs the `luxnix-ca-trust-repair` command.

`luxnix.generic-settings` points `SSL_CERT_FILE`, `NIX_SSL_CERT_FILE` and the
Nix daemon `ssl-cert-file` at `config.security.pki.caBundle` and no longer
installs the unfiltered `cacert` into the system profile. The lx-annotate
service environment sets `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` and
`NIX_SSL_CERT_FILE` to the same bundle. Nix-built `certifi` honours
`NIX_SSL_CERT_FILE`.

## Repair action

`pip` installs `certifi` with its own `cacert.pem`, and `pip` vendors
another copy under `pip/_vendor/certifi/`. These files ignore the NixOS trust
store, and every reinstall restores them.

```bash
luxnix-ca-trust-repair <venv>...           # relink to the system bundle
luxnix-ca-trust-repair --check <venv>...   # exit 1 on any stale bundle
```

The repair replaces `site-packages/certifi/cacert.pem` and
`site-packages/*/_vendor/certifi/cacert.pem` with symlinks to the regenerated
system bundle. Run it as the environment owner. The command only covers
`certifi`; packages that ship other bundles are not changed.

The lx-annotate wheel runtime runs it automatically:

- `lx-annotate-wheel-runtime.service` repairs the wheel venv after every
  install check, under the installer lock.
- Application entry points run `--check` and refuse to start a runtime
  whose `certifi` bundles were not repaired.

The runtime package embeds the bundle path, so a trust-store change restarts
`lx-annotate-wheel-runtime.service` on activation, which re-runs the repair.

## Operations

The change takes effect on the next activation of each host through the
normal [deployment workflow](deployment-guide.md). After activation:

```bash
readlink -f /etc/ssl/certs/ca-certificates.crt
systemctl status lx-annotate-wheel-runtime.service
```

Rebuild any container images built outside Nix without layer caching so
they pick up the updated system certificates.

## Removing an entry

Once a nixpkgs update ships an NSS release without these roots (cacert
3.131.1 or later), the build check fails with "distrusted labels are not in
the pinned cacert". Remove those labels from
`luxnix.caTrust.distrustedCertificates` in the same change as the
`flake.lock` update.
