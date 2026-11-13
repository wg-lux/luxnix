# Remote annotation tunnel

Use this to work in another host's lx-annotate from the controller desktop:
review and edit videos, add annotations, and mark resources for hub export on
`gc-05` or any other GPU client, without sitting at that machine.

```bash
devenv shell lx-annotate-tunnel gc-05               # annotate videos
devenv shell lx-annotate-tunnel gc-05 --hub-export  # start on Hub Export
```

A Firefox window opens on the target's lx-annotate. Sign in with your own
Keycloak account, work as you would locally, and close the window to end the
tunnel. Run the command again with another host for a second, independent
window.

## Why a tunnel is needed

GPU clients serve lx-annotate under the machine-local name
`lx-annotate.local`. That name resolves only on the host itself, and port 443
is closed on the VPN interface. The wrapper therefore lets the browser connect
from inside the target:

```text
Firefox profile for <host>  ->  SOCKS on 127.0.0.1  ->  ssh <host>
  ->  sshd opens lx-annotate.local:443 on <host>  ->  nginx  ->  lx-annotate
```

The address bar still shows `https://lx-annotate.local/`, so cookies and the
Keycloak callback are the same as for a browser on the host. Only the Keycloak
login page is loaded directly from the controller.

## One-time enablement per host

SSH forwarding is disabled fleet-wide. A host accepts the tunnel only after it
runs a configuration with

```nix
services.luxnix.lxAnnotateLocal.remoteAccess.sshTunnel.enable = true;
```

The inventory sets this for the `gpu_client` group in
`ansible/inventory/group_vars/gpu_client.yml`. With it, sshd on that host uses
`AllowTcpForwarding local` and `PermitOpen <its lx-annotate name>:443`: the
admin SSH account can forward to that one destination and to nothing else.
Remote forwarding, agent forwarding and X11 forwarding stay off, and hosts
without the option keep `AllowTcpForwarding no`.

Activate the change on each target with the reviewed checkout, following the
[Deployment Guide](deployment-guide.md):

```bash
devenv shell check-connectivity <host>
sudo nixos-rebuild switch --flake '<checkout>#<host>'   # on the target
```

Until then the wrapper stops with `the tunnel cannot reach
lx-annotate.local:443`.

## What the wrapper does

1. Checks that the host is in `ansible/inventory/hosts.ini` and reads its
   lx-annotate name from the host variables (default `lx-annotate.local`).
2. Reads over SSH whether `lx-annotate`, `nginx` and the hub transfer units are
   active, and the SHA-256 fingerprint of the host's public TLS certificate.
   It stops when the application is not running and warns when hub transfer is
   not ready.
3. Opens the tunnel on a free loopback port and confirms that the host accepts
   the forward.
4. Starts Firefox with a private profile under
   `~/.local/state/luxnix/lx-annotate-tunnel/<host>/`, one per host.

The wrapper itself changes nothing on the target. Annotations and hub-export
marking are made by the signed-in user in the application and audited there.

### First use on a host

GPU clients use a self-signed certificate, so Firefox shows a warning once per
host. Compare the SHA-256 fingerprint in the warning (**Advanced → View
Certificate**) with the one the wrapper printed. Accept the exception only when
they match. The profile remembers it; a later warning means the certificate
changed and must be checked again.

### Working on the right machine

The controller runs its own lx-annotate under the same name. The tunnel profile
has no direct route to that name: when the tunnel closes, pages stop loading
instead of silently switching to the controller's instance. Still confirm the
center shown in the application before annotating, and keep one window per
host.

## Starting a hub transfer

Open the host with `--hub-export`, then follow the daily workflow in the
[Clinical Hub Transfer Guide](clinical-hub-transfer-guide.md): check the
destination and privacy summary, select the intended resource and choose
**Für Hub markieren**. The target's own `hub_transfer` worker sends the data to
the hub over mTLS. Nothing travels through the controller or the tunnel except
the browser session.

If the wrapper warns that hub transfer services are not active, marking still
works but nothing is sent until an administrator restores them.

## Options

| Option | Effect |
| --- | --- |
| `--hub-export` | Start on `/hub-export`. |
| `--page <path>` | Start on another absolute path. |
| `--port <port>` | Use a fixed loopback port instead of a free one. |
| `--no-browser` | Hold the tunnel open and print the SOCKS endpoint for a manually configured browser profile. |
| `--dry-run` | Print the resolved host, URL, SSH command and profile path without connecting. |

## Troubleshooting

| Message | Meaning and next step |
| --- | --- |
| `SSH to <host> failed` | The host is off, asleep or not reachable in the VPN. Run `devenv shell check-connectivity <host>`. |
| `the tunnel cannot reach …:443` | The host does not run the tunnel configuration yet. Deploy it as described above. |
| `lx-annotate.service … not active` | The application is stopped, often because the data volume is locked. Run `sudo luxnix-operator-storage start` on the host. |
| Keycloak rejects the login | The account lacks the role for that center. Ask the administrator; do not share accounts. |
| Pages stop loading | The tunnel closed. Close the window and start the command again. |

The profile directory holds the session cookie of the signed-in user. It is
created with mode `0700`; delete it to remove the stored session and
certificate exception for a host.
