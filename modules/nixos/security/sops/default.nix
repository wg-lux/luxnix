{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.security.sops;
  keyCfg = cfg.operatorStorageKey;
  storage = config.luxnix.storage.operatorUnlocked;
  bootStorage = storage.enable && storage.layout == "boot-luks";
  hostName = config.networking.hostName;
  keyVolume = storage.volumes.${keyCfg.volume} or null;
  keyMountPoint =
    if keyVolume != null then
      keyVolume.mountPoint
    else
      throw "security.sops.operatorStorageKey.volume ${keyCfg.volume} is not an operator-unlocked storage volume.";
  keyDirectory = "${keyMountPoint}/${keyCfg.directory}";
  keyFile = "${keyDirectory}/keys.txt";
  regularSecrets = filterAttrs (_: secret: !secret.neededForUsers) config.sops.secrets;
  applicationPaths = mapAttrsToList (_: secret: secret.path) keyCfg.applicationSecrets;
  volumeKeyName = volume: "volume-key-${volume}";
  repository = keyCfg.secretsRepository;
  # Fetched only when this host uses sops secrets; a flake input would be
  # fetched for every host and break evaluation without repository access.
  pinnedSecretsFile =
    if repository.url != null && repository.rev != null then
      "${
        builtins.fetchGit {
          inherit (repository) url rev;
          allRefs = true;
        }
      }/hosts/${hostName}.yaml"
    else
      null;
  githubHostKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl";
  verifyStorage = "${pkgs.python3}/bin/python3 ${../../../../lx_administration/secret_storage.py}";

  # One host command for the production setup path: create the age key, enroll
  # an installed volume key into its existing LUKS container, report state.
  storageTool = pkgs.writeShellApplication {
    name = "luxnix-sops-storage";
    runtimeInputs = [
      pkgs.age
      pkgs.coreutils
      pkgs.cryptsetup
      pkgs.openssh
      pkgs.systemd
      pkgs.util-linux
    ];
    text = ''
      umask 077
      mount_point=${escapeShellArg keyMountPoint}
      directory=${escapeShellArg keyDirectory}
      key=${escapeShellArg keyFile}
      host=${escapeShellArg hostName}
      deploy_key=${escapeShellArg repository.deployKey}
      declare -A volume_state=(${
        concatStrings (mapAttrsToList (n: s: " [${n}]=${s}") keyCfg.volumeKeys)
      } )
      declare -A volume_container=(${
        concatStrings (
          mapAttrsToList (
            n: _: " [${n}]=${escapeShellArg (toString (storage.volumes.${n}.container or ""))}"
          ) keyCfg.volumeKeys
        )
      } )
      declare -A volume_key=(${
        concatStrings (
          mapAttrsToList (
            n: _: " [${n}]=${escapeShellArg config.sops.secrets.${volumeKeyName n}.path}"
          ) keyCfg.volumeKeys
        )
      } )
      application_paths=(${escapeShellArgs applicationPaths})

      die() {
        echo "ERROR: $*" >&2
        exit 1
      }

      require_root() {
        [ "$(id -u)" -eq 0 ] || die "run as root: sudo luxnix-sops-storage $1"
      }

      require_key_volume() {
        ${optionalString (!bootStorage)
          ''mountpoint -q "$mount_point" || die "$mount_point is not mounted; unlock operator storage first."''
        }
        ${verifyStorage} "$mount_point" || die "$mount_point is not on encrypted storage."
      }

      cmd_init() {
        require_root init
        require_key_volume
        if [ ! -e "$key" ]; then
          [ -d "$directory" ] || mkdir -m 0700 "$directory"
          temporary="$(mktemp "$directory/.keys.XXXXXX")"
          age-keygen 2>/dev/null > "$temporary"
          chmod 0400 "$temporary"
          mv -n "$temporary" "$key"
          echo "Created $key." >&2
        fi
        echo "age recipient for $host (add to the private secrets repository):"
        age-keygen -y "$key"
        # Read-only access to ciphertext for on-host builds; useless without the age key.
        if [ ! -e "$deploy_key" ]; then
          install -d -m 0700 "$(dirname "$deploy_key")"
          ssh-keygen -q -t ed25519 -N "" -C "luxnix-secrets-deploy@$host" -f "$deploy_key"
          echo "Created $deploy_key." >&2
        fi
        echo "read-only deploy key for $host (add to the private repository's deploy keys):"
        cat "$deploy_key.pub"
      }

      key_enrolled() {
        cryptsetup open --test-passphrase --key-file "''${volume_key[$1]}" "''${volume_container[$1]}" 2>/dev/null
      }

      cmd_enroll() {
        local volume="''${1:-}"
        require_root "enroll <volume>"
        [ -n "$volume" ] && [[ -v "volume_state[$volume]" ]] \
          || die "usage: luxnix-sops-storage enroll <volume>; configured volume keys: ''${!volume_state[*]}"
        [ -t 0 ] || die "enroll requires an interactive terminal for the existing passphrase."
        [ -s "''${volume_key[$volume]}" ] \
          || die "''${volume_key[$volume]} is not installed; deploy volumeKeys.$volume = \"staged\" and check sops-install-secrets.service."
        if key_enrolled "$volume"; then
          echo "$volume: volume key already enrolled."
          return 0
        fi
        echo "Enter an existing passphrase of $volume. It stays enrolled as the recovery path."
        cryptsetup luksAddKey "''${volume_container[$volume]}" "''${volume_key[$volume]}"
        key_enrolled "$volume" || die "$volume: the volume key was not accepted after enrollment."
        echo "$volume: volume key enrolled. Next: set volumeKeys.$volume = \"active\" and switch."
      }

      cmd_status() {
        require_root status
        local failed=0 volume path
        report() {
          if [ "$1" = ok ]; then echo "ok    $2"; else echo "FAIL  $2"; failed=1; fi
        }
        if mountpoint -q "$mount_point"; then report ok "$mount_point mounted"; else report fail "$mount_point mounted"; fi
        if [ -s "$key" ]; then
          report ok "age key present (recipient $(age-keygen -y "$key"))"
        else
          report fail "age key present: run 'sudo luxnix-sops-storage init'"
        fi
        ${optionalString (regularSecrets != { }) ''
          if systemctl is-active --quiet sops-install-secrets.service; then
            report ok "sops-install-secrets.service active"
          else
            report fail "sops-install-secrets.service active: journalctl -u sops-install-secrets.service -b"
          fi
        ''}
        # Installed means resolving into sops-nix's ramfs, never a stale plaintext copy.
        for path in "''${application_paths[@]}"; do
          if [ -s "$path" ] && [[ "$(readlink -f "$path")" == /run/secrets.d/* ]]; then
            report ok "$path installed"
          else
            report fail "$path installed"
          fi
        done
        for volume in "''${!volume_state[@]}"; do
          if [ ! -s "''${volume_key[$volume]}" ]; then
            report fail "$volume: volume key installed"
            continue
          fi
          if key_enrolled "$volume"; then
            report ok "$volume: volume key enrolled (''${volume_state[$volume]})"
          else
            report fail "$volume: volume key enrolled: run 'sudo luxnix-sops-storage enroll $volume'"
          fi
          if [ "''${volume_state[$volume]}" = active ]; then
            if cryptsetup status "$volume" >/dev/null 2>&1; then report ok "$volume: open"; else report fail "$volume: open"; fi
          fi
        done
        return "$failed"
      }

      case "''${1:-}" in
        init) cmd_init ;;
        enroll) shift; cmd_enroll "$@" ;;
        status) cmd_status ;;
        *) die "usage: luxnix-sops-storage init | enroll <volume> | status" ;;
      esac
    '';
  };
in
{
  options.security.sops = with types; {
    enable = mkBoolOpt false "Whether to enable sop for secrets management.";

    operatorStorageKey = {
      enable = mkBoolOpt false ''
        Decrypt sops secrets with a per-host age key stored on an operator-unlocked
        encrypted volume instead of the SSH host key. Secrets are installed by a
        systemd unit after that volume opens, never during early boot.
      '';
      volume = mkOpt str "luxnix-secrets" "Operator-unlocked volume holding the age key.";
      directory = mkOpt str "sops-age" "Directory on that volume for the age key.";
      consumers = mkOpt (listOf str) [ ] "Services that require installed sops secrets.";
      secretsRepository = {
        url =
          mkOpt (nullOr str) null
            "SSH URL of the private secrets repository, for example ssh://git@github.com/<org>/<repo>.git.";
        rev = mkOpt (nullOr (
          strMatching "[0-9a-f]{40}"
        )) null "Reviewed commit of the private secrets repository, pinned in inventory.";
        deployKey =
          mkOpt str "/root/.ssh/luxnix-secrets-deploy"
            "Read-only deploy key root uses to fetch the repository during on-host builds.";
      };
      secretsFile = mkOption {
        type = nullOr path;
        default = pinnedSecretsFile;
        defaultText = literalExpression ''"<secretsRepository at rev>/hosts/<host>.yaml"'';
        description = ''
          Encrypted sops file for this host, by default hosts/<host>.yaml from the
          pinned private secrets repository. Only ciphertext enters the Nix store.
        '';
      };
      applicationSecrets = mkOption {
        default = { };
        description = ''
          Explicit host-export secrets moved from sync-secrets to sops, keyed by
          their export file name. deploy_secrets.yml stops writing these names.
          Never list secrets needed before storage unlock.
        '';
        type = attrsOf (
          submodule (
            { name, ... }:
            {
              options = {
                path = mkOpt str "/etc/secrets/vault/${name}" "Installed path kept for existing consumers.";
                owner = mkOpt str "root" "Owner of the installed secret.";
                group = mkOpt str "root" "Group of the installed secret.";
                mode = mkOpt str "0400" "Mode of the installed secret.";
                restartUnits = mkOpt (listOf str) [ ] "Units restarted when the secret changes.";
              };
            }
          )
        );
      };
      volumeKeys = mkOption {
        type = attrsOf (enum [
          "staged"
          "active"
        ]);
        default = { };
        description = ''
          Operator-unlocked volumes opened automatically from a sops-installed key
          (sops key `volume-key-<volume>`). "staged" installs the key while the
          volume still prompts, so it can be enrolled with
          `luxnix-sops-storage enroll`; "active" unlocks with it.
        '';
      };
    };
  };

  config = mkMerge [
    (mkIf cfg.enable {
      sops = {
        defaultSopsFile = ../../secrets.yaml;
        defaultSopsFormat = "yaml";
        age.sshKeyPaths = mkIf (!keyCfg.enable) [ "/etc/ssh/ssh_host_ed25519_key" ];
      };
    })

    (mkIf keyCfg.enable {
      assertions = [
        {
          assertion = cfg.enable && storage.enable;
          message = "security.sops.operatorStorageKey requires security.sops and operator-unlocked storage.";
        }
        {
          assertion = keyVolume != null && (bootStorage || keyVolume.container != null);
          message = "security.sops.operatorStorageKey.volume must name an operator-unlocked container volume.";
        }
        {
          assertion =
            (keyCfg.applicationSecrets == { } && keyCfg.volumeKeys == { }) || keyCfg.secretsFile != null;
          message = "sops application secrets and volume keys require secretsFile, normally from secretsRepository.url and rev.";
        }
        {
          assertion = (repository.url == null) == (repository.rev == null);
          message = "security.sops.operatorStorageKey.secretsRepository needs both url and rev.";
        }
        {
          assertion =
            (!bootStorage || keyCfg.volumeKeys == { })
            && all (
              volume:
              volume != keyCfg.volume
              && storage.volumes ? ${volume}
              && storage.volumes.${volume}.container != null
            ) (attrNames keyCfg.volumeKeys);
          message = "security.sops.operatorStorageKey.volumeKeys must name other operator-unlocked container volumes, never the age key volume.";
        }
        {
          assertion = all (path: hasPrefix "/" path && !hasPrefix "/nix/store/" path) applicationPaths;
          message = "sops application secret paths must be absolute and outside the Nix store.";
        }
        {
          # Account credentials are needed before storage unlock.
          assertion =
            !any (
              name:
              elem name [
                (baseNameOf config.luxnix.vault.adminPasswordFile)
                (baseNameOf config.luxnix.vault.adminPasswordHashedFile)
                "SCRT_client_user_password"
                "SCRT_client_user_password_hash"
              ]
            ) (attrNames keyCfg.applicationSecrets);
          message = "Account passwords stay with their boot-copy workflow and must not be sops application secrets.";
        }
        {
          assertion = !any (secret: secret.neededForUsers) (attrValues config.sops.secrets);
          message = "sops secrets on operator storage are unavailable when accounts are created; keep account hashes on the boot copy instead of neededForUsers.";
        }
      ];

      environment.systemPackages = [ storageTool ];

      # Root fetches the pinned repository over SSH during nixos-rebuild.
      programs.ssh = mkIf (repository.url != null) {
        knownHosts."github.com".publicKey = githubHostKey;
        extraConfig = ''
          Match localuser root host github.com
            IdentityFile ${repository.deployKey}
            IdentitiesOnly yes
        '';
      };

      # No offline-readable identity may decrypt: the SSH host keys sit on an
      # unencrypted root on some hosts.
      sops = {
        age = {
          inherit keyFile;
          sshKeyPaths = [ ];
          generateKey = false;
        };
        gnupg.sshKeyPaths = [ ];
        useSystemdActivation = true;
        secrets =
          mapAttrs (_: secret: {
            inherit (secret)
              path
              owner
              group
              mode
              restartUnits
              ;
            sopsFile = keyCfg.secretsFile;
          }) keyCfg.applicationSecrets
          // mapAttrs' (
            volume: _:
            nameValuePair (volumeKeyName volume) {
              sopsFile = keyCfg.secretsFile;
              mode = "0400";
            }
          ) keyCfg.volumeKeys;
      };

      luxnix.storage.operatorUnlocked.volumes = mapAttrs (volume: state: {
        keyFile = mkIf (state == "active") config.sops.secrets.${volumeKeyName volume}.path;
      }) keyCfg.volumeKeys;

      systemd.services =
        genAttrs (map (removeSuffix ".service") keyCfg.consumers) (_: {
          requires = [ "sops-install-secrets.service" ];
          after = [ "sops-install-secrets.service" ];
        })
        // {
          # Upstream runs this unit in sysinit; its RequiresMountsFor on the key
          # would pull the passphrase prompt into early boot. Run it as a normal
          # service once the key volume is open, and leave account setup alone.
          sops-install-secrets = mkIf (regularSecrets != { }) {
            wantedBy = mkForce [ "multi-user.target" ];
            requiredBy = mkForce [ ];
            before = mkForce [ ];
            after = mkForce (
              [ "local-fs.target" ] ++ optional (!bootStorage) "luxnix-storage-unlock-${keyCfg.volume}.service"
            );
            unitConfig = {
              DefaultDependencies = mkForce "yes";
              # Installed paths such as /etc/secrets/vault are binds on the volume;
              # /run/secrets is sops-nix's own ramfs link, not a mount.
              RequiresMountsFor = filter (dir: dir != "/run/secrets") (unique (map dirOf applicationPaths));
            };
            path = [ pkgs.util-linux ];
            serviceConfig.ExecStartPre = [ "${verifyStorage} ${keyDirectory}" ];
          };
        };
    })
  ];
}
