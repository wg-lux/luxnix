{
  config,
  lib,
  pkgs,
  # Snowfall does not forward lazily supplied module arguments.
  utils ? config._module.args.utils,
  ...
}:
let
  cfg = config.luxnix.storage.operatorUnlocked;
  # Mapping name (from /dev/mapper/<name>) to the declared container, or "".
  containers = lib.mapAttrs' (
    _: volume:
    lib.nameValuePair (lib.removePrefix "/dev/mapper/" volume.device) (
      if volume.container == null then "" else volume.container
    )
  ) cfg.volumes;

  # Unlocks only existing containers at cryptsetup's hidden prompt. It never
  # formats storage. start opens mappings, then uses the normal guarded units.
  storageTool = pkgs.writeShellApplication {
    name = "luxnix-operator-storage";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.cryptsetup
      pkgs.gnused
      pkgs.python3
      pkgs.util-linux
      pkgs.systemd
    ];
    text = ''
      declare -A containers=(
      ${
        lib.concatStrings (
          lib.mapAttrsToList (name: path: "  [${name}]=${lib.escapeShellArg path}\n") containers
        )
      })
      mappings=(${lib.escapeShellArgs (builtins.attrNames containers)})

      die() {
        echo "ERROR: $*" >&2
        exit 1
      }

      usage() {
        cat >&2 <<'EOF'
      Usage: luxnix-operator-storage status
             luxnix-operator-storage open [mapping...]
             luxnix-operator-storage start
             luxnix-operator-storage enroll-tpm2 <mapping>
             luxnix-operator-storage header-backup <mapping> <destination-file>
      EOF
        exit 2
      }

      require_declared() {
        [[ -v "containers[$1]" ]] || die "$1 is not a declared mapping (declared: ''${mappings[*]})."
      }

      require_container() {
        local container="''${containers[$1]}"
        [ -n "$container" ] \
          || die "$1 has no confirmed backing container; record it in inventory after the recovery operator confirms it."
        [ -f "$container" ] && [ ! -L "$container" ] \
          || die "$container is missing or not a regular file. Never recreate or format it."
      }

      # Prints the backing file of an active mapping; fails when it is closed.
      active_backing() {
        local status
        status="$(cryptsetup status "$1" 2>/dev/null)" || return 1
        sed -n 's/^ *loop: *//p' <<<"$status"
      }

      verify_backing() {
        local name="$1" backing="$2" container="''${containers[$1]}"
        if [ -z "$container" ]; then
          echo "$name: open from ''${backing:-a non-file device}, but no backing container is declared" >&2
          return 1
        fi
        if [ -z "$backing" ] || [ "$backing" != "$(realpath -e "$container")" ]; then
          echo "$name: open from ''${backing:-a non-file device}, expected $container" >&2
          return 1
        fi
      }

      cmd_status() {
        [ "$#" -eq 0 ] || usage
        local failed=0 name backing target
        for name in "''${mappings[@]}"; do
          if ! backing="$(active_backing "$name")"; then
            echo "$name: locked"
            failed=1
            continue
          fi
          if ! verify_backing "$name" "$backing"; then
            failed=1
            continue
          fi
          target="$(findmnt --noheadings --output TARGET --source "/dev/mapper/$name" | head -n 1 || true)"
          echo "$name: open from $backing, ''${target:+mounted at }''${target:-not mounted}"
        done
        return "$failed"
      }

      cmd_open() {
        ${lib.optionalString (cfg.unlockMethod == "passphrase") ''
          [ -t 0 ] || die "open requires an interactive terminal; never pipe or pass passphrases."
        ''}
        local name backing
        local selected=("$@")
        [ "''${#selected[@]}" -gt 0 ] || selected=("''${mappings[@]}")
        for name in "''${selected[@]}"; do
          require_declared "$name"
        done
        for name in "''${selected[@]}"; do
          if backing="$(active_backing "$name")"; then
            verify_backing "$name" "$backing" || die "Refusing to continue with a mismatched mapping."
            echo "$name: already open from $backing"
            continue
          fi
          # Mount declared backing filesystems before looking for container files.
          case "$name" in
          ${lib.concatStrings (
            lib.mapAttrsToList (
              _: volume:
              "${lib.escapeShellArg (lib.removePrefix "/dev/mapper/" volume.device)}) "
              + (
                if volume.depends == [ ] then
                  ":"
                else
                  "systemctl start "
                  + lib.escapeShellArgs (map (path: "${utils.escapeSystemdPath path}.mount") volume.depends)
              )
              + ";;\n"
            ) cfg.volumes
          )}
          esac
          case "$name" in
            ${lib.concatStrings (
              lib.mapAttrsToList (
                volumeName: volume:
                "${lib.escapeShellArg (lib.removePrefix "/dev/mapper/" volume.device)}) systemctl start ${lib.escapeShellArg "luxnix-storage-unlock-${volumeName}.service"};;\n"
              ) (lib.filterAttrs (_: volume: volume.container != null) cfg.volumes)
            )}
            *) die "$name requires an externally opened mapping." ;;
          esac
        done
        echo "Mappings verified. Use luxnix-operator-storage start to start configured consumers."
      }

      cmd_header_backup() {
        [ "$#" -eq 2 ] || usage
        local name="$1" destination="$2" container parent source mapping
        require_declared "$name"
        require_container "$name"
        container="''${containers[$name]}"
        case "$destination" in
          /*) ;;
          *) die "The destination must be an absolute path." ;;
        esac
        [ ! -e "$destination" ] && [ ! -L "$destination" ] || die "$destination already exists."
        parent="$(dirname "$destination")"
        [ -d "$parent" ] || die "$parent does not exist."
        python3 -I ${../../../../lx_administration/secret_storage.py} "$destination" \
          || die "Header backups require persistent encrypted storage."
        [ "$(stat -c %d "$parent")" != "$(stat -c %d "$container")" ] \
          || die "Store the header backup on a different filesystem than $container."
        source="$(findmnt --noheadings --output SOURCE --target "$parent" | head -n 1)"
        source="$(realpath -e "''${source%%\[*}")"
        for mapping in "''${mappings[@]}"; do
          if [ -e "/dev/mapper/$mapping" ] && [ "$source" = "$(realpath -e "/dev/mapper/$mapping")" ]; then
            die "Header backups must not be stored inside an operator-unlocked volume."
          fi
        done
        (umask 077 && cryptsetup luksHeaderBackup "$container" --header-backup-file "$destination")
        chmod 0400 "$destination"
        echo "Header backup of $name written to $destination."
        echo "It opens with every passphrase in its keyslots: keep it in approved recovery custody and"
        echo "replace it after any keyslot change, because a stale backup still accepts removed passphrases."
      }

      [ "$#" -ge 1 ] || usage
      command="$1"
      shift
      [ "$(id -u)" -eq 0 ] || die "Run as root (sudo)."
      ${lib.optionalString (cfg.unlockMethod == "passphrase") ''
        if [[ "$command" == open || "$command" == start ]]; then
          [ -t 0 ] || die "Unlock requires a private interactive terminal."
          systemd-tty-ask-password-agent --watch &
          password_agent=$!
          trap 'kill "$password_agent" 2>/dev/null || true' EXIT
        fi
      ''}
      case "$command" in
        enroll-tpm2)
          [ "$#" -eq 1 ] || usage
          [ -t 0 ] || die "Enrollment requires a private interactive terminal."
          require_declared "$1"
          require_container "$1"
          python3 -c 'import runpy, sys; runpy.run_path(sys.argv[1])["require_secure_boot"]()' \
            ${../../../../lx_administration/storage/operator_migration.py}
          # Add a hardware slot; preserve every existing recovery passphrase slot.
          systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 --tpm2-with-pin=no \
            "''${containers[$1]}"
          ;;
        status) cmd_status "$@" ;;
        open) cmd_open "$@" ;;
        start)
          [ "$#" -eq 0 ] || usage
          ${lib.optionalString (cfg.startupServices == [ ]) ''die "No startupServices configured."''}
          cmd_open
          systemctl start ${lib.escapeShellArgs (map (name: "${name}.service") cfg.startupServices)}
          ;;
        header-backup) cmd_header_backup "$@" ;;
        *) usage ;;
      esac
    '';
  };
in
{
  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ storageTool ];
  };
}
