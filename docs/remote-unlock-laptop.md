# Remote root unlock on a laptop

This guide sets up SSH root unlock on one laptop whose root disk already uses
boot-time LUKS2 (`storage.operatorUnlocked.layout: "boot-luks"`). After a
reboot, the laptop waits in early boot for the disk passphrase. With remote
unlock enabled you can type that passphrase over SSH from a trusted computer on
the same LAN instead of at the laptop's keyboard.

The general rules, the reasons behind them and the physical acceptance stages
are in [Boot LUKS storage migration: remote SSH root unlock](boot-storage-migration.md#remote-ssh-root-unlock)
and the `remote_unlock` section of
[boot-storage.yml](https://github.com/wg-lux/luxnix/blob/main/boot-storage.yml).
This page is the step-by-step procedure for a laptop.

## What you get and what you do not

- Port 2222 on a fixed wired address accepts one dedicated SSH key per operator
  and only asks for the disk passphrase. It cannot run commands, forward ports
  or open a shell.
- The passphrase prompt on the laptop's own screen keeps working at the same
  time. Whichever answer arrives first unlocks root.
- Secondary storage is **not** unlocked by this. After boot, connect with normal
  SSH and run `sudo luxnix-operator-storage start` as usual.
- Early boot has **no Wi-Fi, no DHCP, no DNS and no OpenVPN**. Only a wired
  connection with a static address on one known LAN works. The `172.16.255.x`
  VPN addresses cannot reach it.

## Is this laptop a good candidate?

Check every item before you change anything. If one fails, keep console
unlock; the laptop then needs someone at its keyboard after each reboot.

| Requirement | Why |
| --- | --- |
| The laptop stays on one LAN, on a wired cable, when remote unlock matters | The early-boot address is static and belongs to that LAN only. Away from it, only console unlock works. |
| A built-in Ethernet port, or one USB/USB-C adapter or dock that always stays in the **same port** | USB network interface names include the port path. A different port gives a different name, and early boot then has no network. |
| A trusted computer that is **running** and on the same LAN, with a LAN address in the inventory | Only LAN addresses of trusted hosts in the same `network_cluster` may connect. It also serves as the jump host for operators who are off site. |
| Fleet Secure Boot is **off** for this host (`system.boot.secureBoot`) | Controller-signed Secure Boot forbids host-local initrd secrets. The two cannot be combined yet. |
| Someone can reach the laptop's keyboard for the first test | The first remote unlock is always attended. |
| The disk passphrase has been verified and is stored off the machine | It is still the only credential the endpoint accepts. |

Keep the laptop on mains power. A laptop on battery survives a short power cut
by itself, so remote unlock mainly matters after planned reboots (kernel and
configuration updates) and after a battery runs flat. If the firmware offers
"power on when AC is connected", that brings the laptop back after a flat
battery; the setting is optional and outside LuxNix.

After boot, the normal system must not suspend when the lid is closed on mains
power, or normal SSH will disappear again. Check the host's logind
`HandleLidSwitchExternalPower` setting before relying on the laptop headless.

## Placeholders used below

| Placeholder | Example | Meaning |
| --- | --- | --- |
| `<host>` | `gc-09` | Laptop inventory name |
| `<iface>` | `enp0s31f6`, `enp0s20f0u2` | Wired interface name on the laptop |
| `<address>` | `192.168.179.40` | Static early-boot address, without prefix |
| `<prefix>` | `24` | LAN prefix length |
| `<gateway>` | `192.168.179.1` | LAN gateway; leave it out when every client is on the same subnet |
| `<trusted host>` | `gc-02` | Running inventory host on the same LAN |
| `<checkout>` | `/home/admin/luxnix` | Reviewed LuxNix checkout |

Always use the real values for the selected laptop. Never copy them from another
host or from an old runbook.

## 1. Find the wired interface and its drivers

On the laptop, booted normally, with the cable (and adapter or dock) plugged in
exactly where it will stay:

```sh
ip -br link
ip -br addr
```

Pick the wired interface that shows `UP` with a LAN address. Built-in ports are
usually called `enp…`. USB adapters are usually called `enp…u<port>` or
`enx<MAC>`. Then list every driver between the network card and the CPU:

```sh
udevadm info --attribute-walk /sys/class/net/<iface> | grep -E 'DRIVERS=="[^"]+"' | sort -u
```

All the drivers listed are needed in early boot. Typical results:

| Hardware | Drivers to list |
| --- | --- |
| Built-in Intel Ethernet | `e1000e` (or `igc`) |
| Built-in Realtek Ethernet | `r8169` |
| USB Realtek adapter | `r8152`, `xhci_pci` |
| USB ASIX adapter | `ax88179_178a`, `xhci_pci` |
| USB-C or Thunderbolt dock | the adapter driver, `cdc_ncm` or `cdc_ether` if listed, `xhci_pci`, and `thunderbolt` if listed |

Ignore generic entries such as `pcieport` and `usb`. Write the interface name
and the driver list down; they go into the inventory in step 5.

Check that the name is stable: unplug the cable or adapter, plug it back in the
same port, and confirm that `ip -br link` shows the same name. If it changes
every time, do not continue with that adapter.

## 2. Choose the early-boot address and trusted clients

1. Choose a free address on the laptop's LAN, outside the DHCP pool, or reserve
   it in the router for the laptop's wired MAC address. When the normal system
   uses DHCP on the same cable, a reservation for that address avoids two
   different addresses on one port.
2. Choose the trusted computers that may unlock the laptop: operator
   workstations or an always-on host on the same LAN. Off-site operators connect
   through one of these as a jump host.
3. In the shared inventory host map
   (`ansible/inventory/group_vars/all/30-nix.yml`), give the laptop a
   `network_cluster`, and give each trusted computer `ip_local` and the same
   `network_cluster`:

   ```yaml
   generic_settings.network.hosts.<host with underscores>.network_cluster: '"L1"'
   generic_settings.network.hosts.<trusted host with underscores>.ip_local: '"<its LAN address>"'
   generic_settings.network.hosts.<trusted host with underscores>.network_cluster: '"L1"'
   ```

   The map uses underscores (`gc_02`); everywhere else the host name keeps its
   hyphen (`gc-02`).

   The cluster also controls `/etc/hosts`: hosts in the same cluster reach each
   other by `ip_local` instead of the VPN address. For a laptop this means its
   cluster peers resolve to LAN addresses even when the laptop is elsewhere, so
   use the VPN address explicitly when off site. Give the laptop its own
   `ip_local` only if its normal address on that LAN is fixed; otherwise peers
   would resolve the laptop to an address it does not have. Remote unlock does
   not need the laptop's `ip_local`.

The allowed source list is derived; you do not write it by hand. It contains the
LAN `/32` of every host in `networkAccess.operatorHosts` (and, on client
laptops, `networkAccess.leaderHosts`) that is in the **same** `network_cluster`.
A trusted host in another cluster is skipped silently. For an operator computer
that is not in the inventory, add its LAN network to
`networkAccess.extraEarlyBootSources` instead (`/16` to `/32`; broader ranges are
rejected).

## 3. Create a dedicated unlock key on each operator computer

Use a new key for unlock only; never reuse a login key.

```sh
ssh-keygen -t ed25519 -f ~/.ssh/luxnix-unlock -C "unlock@$(hostname)"
```

Give it a passphrase. Only the public key (`~/.ssh/luxnix-unlock.pub`) goes into
the inventory.

## 4. Create and pin the laptop's early-boot host identity

The laptop needs a generation built from this release, which contains the helper
`luxnix-setup-remote-unlock`. On the laptop:

```sh
sudo luxnix-setup-remote-unlock
```

It checks that root is really encrypted, creates
`/etc/luxnix/initrd-ssh/ssh_host_ed25519_key` once on the encrypted root and
prints a line like:

```text
[<early-boot address>]:2222 ssh-ed25519 AAAA…
```

Running it again keeps the same identity and prints the line again. Copy the
line through a trusted channel (not over an unverified connection) into
`~/.ssh/known_hosts.luxnix-unlock` on every operator computer and jump host.
Replace `<early-boot address>` with `<address>` if the command could not fill it
in yet.

This key is not a login key: it is copied into the unencrypted initrd and only
identifies the unlock endpoint.

## 5. Enable it in the laptop's inventory

In `ansible/inventory/host_vars/<host>.yml`, under `host_luxnix`:

```yaml
host_luxnix:
  # Trusted computers allowed to unlock root from the LAN (see step 2).
  networkAccess.operatorHosts: '[ "<trusted host>" ]'
  storage.operatorUnlocked.remoteUnlock.enable: "true"
  storage.operatorUnlocked.remoteUnlock.interface: '"<iface>"'
  storage.operatorUnlocked.remoteUnlock.kernelModules: '[ "r8152" "xhci_pci" ]'
  storage.operatorUnlocked.remoteUnlock.address: '"<address>/<prefix>"'
  # Only when a client is in another subnet:
  storage.operatorUnlocked.remoteUnlock.gateway: '"<gateway>"'
  storage.operatorUnlocked.remoteUnlock.authorizedKeys: >-
    [ "ssh-ed25519 AAAA… unlock@operator-a" "ssh-ed25519 AAAA… unlock@operator-b" ]
```

Use the driver list from step 1 for `kernelModules`. Leave `port` at 2222 unless
the LAN requires another one.

## 6. Regenerate, check and stage

From the checkout on the controller:

```sh
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
nix eval --json '.#nixosConfigurations.<host>.config.luxnix.storage.operatorUnlocked.remoteUnlock' \
  --apply 'r: { inherit (r) enable interface kernelModules address gateway port allowedSources; }'
nix build '.#nixosConfigurations.<host>.config.system.build.toplevel' --no-link --print-out-paths
```

Compare the `nix eval` output with your notes. `allowedSources` must contain the
LAN `/32` of each trusted computer and nothing you did not intend. An empty
list does not evaluate; see [Troubleshooting](#troubleshooting).

Install the generation for the **next boot** only, following the
[deployment guide](deployment-guide.md), for example on the laptop:

```sh
sudo nixos-rebuild boot --flake '<checkout>#<host>'
readlink -f /nix/var/nix/profiles/system
```

The second command must print the store path from `nix build`. If the host
identity from step 4 is missing, installation stops and names the command to
run.

## 7. First unlock, attended

Do this one laptop at a time, with someone at the laptop's keyboard who knows
the disk passphrase and can choose the previous generation in the boot menu.

Add an entry to `~/.ssh/config` on each operator computer:

```sshconfig
Host <host>-unlock
  HostName <address>
  Port 2222
  User root
  IdentityFile ~/.ssh/luxnix-unlock
  IdentitiesOnly yes
  UserKnownHostsFile ~/.ssh/known_hosts.luxnix-unlock
  StrictHostKeyChecking yes
  RequestTTY force
  # Only for operators who are not on the laptop's LAN:
  # ProxyJump admin@<trusted host>
```

1. Reboot the laptop. The passphrase prompt appears on its screen; the person
   at the keyboard waits.
2. From the operator computer run `ssh <host>-unlock`. Expect the message
   *Enter the disk recovery passphrase. This connection cannot run other
   commands.*, then type the disk passphrase.
3. The laptop continues booting and the SSH connection closes. Wait a minute,
   then connect with normal SSH, run `sudo luxnix-operator-storage start` if the
   host has guarded services, and check that the booted generation is the
   staged one:
   `readlink -f /run/booted-system` must equal the `nix build` path.
4. Repeat the unlock once from each trusted computer, and once through the jump
   host if off-site operators will use it.

Only after these pass, rely on remote unlock for this laptop. Record what you
observed (never the passphrase) in the private
`cmdb/boot-access-checks/` directory on the controller, as described in
[boot-storage.yml](https://github.com/wg-lux/luxnix/blob/main/boot-storage.yml).

## Daily use

```sh
ssh <host>-unlock                 # while the laptop waits at the passphrase prompt
ssh admin@<host>                  # after boot
sudo luxnix-operator-storage start
```

Before you reboot a laptop remotely, make sure it is on its usual cable and LAN
and that a trusted computer on that LAN is running. Do not reboot the laptop
and its only jump host together: neither could unlock the other.

## Changing keys or turning it off

- **Add or remove an operator:** edit `authorizedKeys`, regenerate, build and
  install with `boot`. The change takes effect at the next reboot.
- **New network adapter, port or address:** repeat steps 1, 2 and 5–7. Update
  the pinned `known_hosts` line if the address changed; the identity stays the
  same.
- **Turn it off:** set `storage.operatorUnlocked.remoteUnlock.enable: "false"`,
  regenerate and install with `boot`. The identity file stays on the encrypted
  root, so turning it on again needs no new pin.

## Troubleshooting

| What you see | Likely cause and fix |
| --- | --- |
| Evaluation: *requires at least one management client network* | No trusted host shares the laptop's `network_cluster`, or a trusted host lacks `ip_local`. Fix the host map or `networkAccess.operatorHosts` (step 2). |
| Evaluation: *requires dedicated Ed25519 operator public keys* | `authorizedKeys` is empty, or an entry is not a single `ssh-ed25519 …` line. |
| Evaluation: *explicit management interface and static address* | `interface` is empty, or `address` lacks `/<prefix>`. |
| Evaluation: *verified early-boot management NIC driver modules* | `kernelModules` is empty; repeat step 1. |
| Evaluation: *Secure Boot does not support boot.initrd.secrets* | Fleet Secure Boot is on for this host. Keep Secure Boot and use console unlock. |
| Installation: *early-boot SSH host identity is missing* | Run step 4 on the laptop, pin the line, install again. |
| `ssh` times out | The laptop is not on its LAN, the adapter is in another port, the cable is out, or a driver is missing. The person at the keyboard types the passphrase; afterwards compare `ip -br link` and step 1. |
| `Connection refused` | Early-boot SSH is still starting; it retries every 5 seconds. Wait and connect again. |
| `Host key verification failed` | Do not accept the new key. The pin is wrong or something else answers at that address. Compare the line from `sudo luxnix-setup-remote-unlock` after a console unlock. |
| `Permission denied (publickey)` | Wrong key file, or the connection comes from an address that is not allowed (for example over Wi-Fi or VPN instead of the LAN, or a jump host that is not trusted). |
| Unlock works, normal SSH does not | The normal system uses another address or interface, or suspended on lid close. Check its network and logind settings at the console. |

Repository VM tests (`nix build .#checks.x86_64-linux.boot-storage-remote --no-link -L`)
exercise the endpoint in a virtual machine only; they do not prove that a
particular laptop, adapter or LAN works. Step 7 does.
