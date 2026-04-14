# Custom NixOS System Settings

LuxNix ships several custom NixOS modules under `modules/nixos/system/`. Each module is opt-in via a boolean `enable` flag and is activated by the roles that depend on them (you rarely need to set these directly in a host's `default.nix`).

---

## `system.nix` — Nix daemon settings

**Source:** [modules/nixos/system/nix/default.nix](../modules/nixos/system/nix/default.nix)

Manages the Nix package manager daemon configuration for all LuxNix hosts.

### Enable

```nix
system.nix.enable = true;
```

### What it configures

#### Trusted users

```nix
nix.settings.trusted-users = [ "@wheel" "root" "admin" "<endoreg-service-user>" ];
```

Members of the `wheel` group, `root`, the `admin` user, and the EndoReg service user are granted trusted-user access to the Nix daemon. Trusted users can pass extra build flags and override substituter settings.

The EndoReg service user name is read from `config.user.endoreg-service-user.name` and resolved at evaluation time.

#### Store optimisation

```nix
nix.settings.auto-optimise-store = lib.mkDefault true;
```

Automatically hard-links identical files in the Nix store after builds. Can be overridden per-host with `lib.mkForce`.

#### XDG base directories

```nix
nix.settings.use-xdg-base-directories = true;
```

Moves per-user Nix state to `$XDG_DATA_HOME/nix` instead of `~/.nix-*`.

#### Experimental features

```nix
nix.settings.experimental-features = [ "nix-command" "flakes" ];
```

Enables the `nix` unified CLI and flake support. Required for all LuxNix operations.

#### Miscellaneous daemon settings

| Setting                | Value              | Effect                                                     |
|------------------------|--------------------|------------------------------------------------------------|
| `warn-dirty`           | `false`            | Suppresses the "git tree is dirty" warning during builds   |
| `system-features`      | `["kvm","big-parallel","nixos-test"]` | Allows KVM builds, large parallel jobs, and NixOS tests |

#### Registry and path generation (flake-utils-plus)

```nix
nix.generateRegistryFromInputs = true;
nix.generateNixPathFromInputs  = true;
nix.linkInputs                 = true;
```

Populates the flake registry and `NIX_PATH` from the flake's `inputs`, so that `nixpkgs` and other inputs are pinned to the exact versions in `flake.lock` rather than fetched from the global registry.

#### Access token include

```nix
nix.extraOptions = ''
  !include /etc/nix/access-tokens.conf
'';
```

Includes `/etc/nix/access-tokens.conf` from the Nix daemon options. This file is managed by the vault and contains GitHub or other substituter tokens. The file may not exist on a freshly installed host; Nix silently ignores a missing `!include` target.

---

## `system.boot` — Boot loader and kernel settings

**Source:** [modules/nixos/system/boot/default.nix](../modules/nixos/system/boot/default.nix)

### Enable

```nix
system.boot = {
  enable         = true;
  plymouth       = false;  # boot splash (optional)
  secureBoot     = false;  # lanzaboote (optional, currently stubbed)
  spaceManagement = true;  # limit systemd-boot entries; default true
};
```

### What it configures

#### EFI boot loader

Uses `systemd-boot` by default:

```nix
boot.loader = {
  efi.canTouchEfiVariables = true;
  systemd-boot = {
    enable              = true;   # false when secureBoot = true
    configurationLimit  = 5;      # 20 when spaceManagement = false
    editor              = false;  # disables boot entry editing
  };
};
```

Keeping `configurationLimit = 5` prevents the EFI system partition from filling up on hosts with frequent rebuilds.

#### initrd systemd

```nix
boot.initrd.systemd.enable = true;
```

Enables the systemd-based initrd, required for LUKS decryption via systemd-cryptsetup (used by `boot-decryption-config.nix`).

#### Plymouth (optional)

When `plymouth = true`:

```nix
boot.kernelParams = [ "quiet" "splash" "loglevel=3" "udev.log_level=0" ];
boot.plymouth.enable = true;
```

#### Socket buffer tuning

Reads from `luxnix.generic-settings.linux.rmemMax` and `luxnix.generic-settings.linux.wmemMax`:

```nix
boot.kernel.sysctl."net.core.rmem_max" = <value>;
boot.kernel.sysctl."net.core.wmem_max" = <value>;
```

High-throughput hosts (group `[high_rmem_wmem]`) get elevated values via the generic-settings configuration.

#### Boot packages

Always installed:

```
efibootmgr  efitools  efivar  fwupd
```

`sbctl` is added when `secureBoot = true`.

---

## `system.locale` — Language and timezone

**Source:** [modules/nixos/system/locale/default.nix](../modules/nixos/system/locale/default.nix)

### Enable

```nix
system.locale.enable = true;
```

### What it configures

Reads `config.luxnix.generic-settings.language`. Hosts in the `[language_english]` inventory group get `"english"`; all others get German.

| Setting             | `language = "english"` | otherwise        |
|---------------------|------------------------|------------------|
| `LANG` / `LC_ALL`   | `en_US.UTF-8`          | `de_DE.UTF-8`    |
| `i18n.defaultLocale`| `en_US.UTF-8`          | `de_DE.UTF-8`    |
| `LC_ADDRESS`        | `en_US.UTF-8`          | `de_DE.UTF-8`    |
| `time.timeZone`     | `Europe/Berlin`        | `Europe/Berlin`  |
| X11 keyboard layout | `de`                   | `de`             |
| Console keymap      | `de`                   | `de`             |

Note: the timezone is always `Europe/Berlin` regardless of language, and measurement/monetary/paper locales always use `de_DE.UTF-8`.

---

## `system.impermanence` — Optional impermanence

**Source:** [modules/nixos/system/impermanence/default.nix](../modules/nixos/system/impermanence/default.nix)

Optional module for impermanence setups (tmpfs root with explicit persistence). Not enabled on any current production host; included for future use.

---

## How these modules are enabled in practice

These modules are enabled by the role and service modules that depend on them — host configs do not typically set `system.nix.enable` directly. For example:

- `roles.common` enables `system.nix`, `system.boot`, and `system.locale`.
- Role modules import what they need, so adding a role to a host automatically pulls in the correct system configuration.

If you need to enable a system module on a host that does not go through a standard role, add the option to the generated config by including the key in `host_luxnix` or by editing the Jinja2 template.

---

## Extending system settings

To add a new system-level Nix option:

1. Edit `modules/nixos/system/nix/default.nix` — add the option under `options.system.nix` and the implementation under `config = mkIf cfg.enable { ... }`.
2. If the option needs to be toggled per-host, expose it as a `mkBoolOpt` or `mkOption`.
3. If the new option depends on a generic-settings value, access it via `config.luxnix.generic-settings.<path>`.

The `lib.luxnix.mkBoolOpt` helper (from `lib/`) is the standard way to define boolean NixOS options with a description:

```nix
options.system.nix = with types; {
  enable     = mkBoolOpt false "Whether or not to manage nix configuration";
  myNewOpt   = mkBoolOpt false "Description of the new option";
};
```
