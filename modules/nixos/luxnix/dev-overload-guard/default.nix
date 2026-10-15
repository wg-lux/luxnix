{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.luxnix.devOverloadGuard;
  hostName = config.networking.hostName or "";
  isDevLaptop =
    hasPrefix "gc-" hostName
    && attrByPath [ "roles" "endoreg-client" "enable" ] false config
    && attrByPath [ "roles" "custom-packages" "baseDevelopment" ] false config;

  guardScript = pkgs.writeTextFile {
    name = "luxnix-dev-overload-guard";
    destination = "/bin/luxnix-dev-overload-guard";
    executable = true;
    text = ''
      #!${pkgs.python3}/bin/python3
      import json
      import os
      import signal
      import subprocess
      import sys
      import time

      STALE_AGE_SECONDS = ${toString cfg.staleAgeSeconds}
      MAX_LOAD1 = ${toString cfg.maxLoad1}
      DRY_RUN = ${if cfg.dryRun then "True" else "False"}
      PATTERNS = [p.lower() for p in ${builtins.toJSON cfg.patterns}]
      PROTECTED_COMMS = {
          "codex",
          "code",
          "bash",
          "dash",
          "fish",
          "sh",
          "zsh",
          "systemd",
      }
      PROTECTED_ARG_MARKERS = (
          "/bin/codex",
          "/codex ",
          "openai.chatgpt",
          "/lib/vscode/code",
          "vscode",
          "visual studio code",
      )


      def emit(event, **fields):
          payload = {
              "event": event,
              "unit": "luxnix-dev-overload-guard",
              **fields,
          }
          print(json.dumps(payload, sort_keys=True), flush=True)


      def load_average():
          try:
              return os.getloadavg()[0]
          except OSError:
              return None


      def read_processes():
          result = subprocess.run(
              [
                  "${pkgs.procps}/bin/ps",
                  "-eo",
                  "pid=,ppid=,pgid=,sid=,etimes=,tty=,comm=,args=",
              ],
              check=True,
              capture_output=True,
              text=True,
          )
          processes = []
          for raw_line in result.stdout.splitlines():
              parts = raw_line.strip().split(None, 7)
              if len(parts) < 8:
                  continue
              pid, ppid, pgid, sid, etimes, tty, comm, args = parts
              try:
                  processes.append(
                      {
                          "pid": int(pid),
                          "ppid": int(ppid),
                          "pgid": int(pgid),
                          "sid": int(sid),
                          "etimes": int(etimes),
                          "tty": tty,
                          "comm": comm,
                          "args": args,
                      }
                  )
              except ValueError:
                  continue
          return processes


      def matches_test_workload(process):
          haystack = f"{process['comm']} {process['args']}".lower()
          return any(pattern in haystack for pattern in PATTERNS)


      def has_tty(processes):
          return any(process["tty"] != "?" for process in processes)


      def has_protected_process(processes):
          for process in processes:
              comm = process["comm"].lower()
              args = process["args"].lower()
              if comm in PROTECTED_COMMS:
                  return True
              if any(marker in args for marker in PROTECTED_ARG_MARKERS):
                  return True
          return False


      def group_summary(group):
          candidate = max(group, key=lambda process: process["etimes"])
          return {
              "pgid": candidate["pgid"],
              "oldest_pid": candidate["pid"],
              "oldest_age_seconds": candidate["etimes"],
              "members": len(group),
              "commands": sorted({process["comm"] for process in group}),
          }


      def terminate_group(pgid, pids):
          if DRY_RUN:
              emit("terminated_group", dry_run=True, pgid=pgid, pids=pids, signal="SIGTERM")
              return

          try:
              os.killpg(pgid, signal.SIGTERM)
              emit("terminated_group", dry_run=False, pgid=pgid, pids=pids, signal="SIGTERM")
          except ProcessLookupError:
              emit("error", pgid=pgid, pids=pids, error="process group disappeared before SIGTERM")
              return
          except PermissionError as exc:
              emit("error", pgid=pgid, pids=pids, error=f"permission denied during SIGTERM: {exc}")
              return

          time.sleep(5)
          remaining = []
          for pid in pids:
              try:
                  os.kill(pid, 0)
                  remaining.append(pid)
              except ProcessLookupError:
                  pass
              except PermissionError:
                  remaining.append(pid)

          if not remaining:
              return

          try:
              os.killpg(pgid, signal.SIGKILL)
              emit("kill_escalated", dry_run=False, pgid=pgid, pids=remaining, signal="SIGKILL")
          except ProcessLookupError:
              pass
          except PermissionError as exc:
              emit("error", pgid=pgid, pids=remaining, error=f"permission denied during SIGKILL: {exc}")


      def main():
          load1 = load_average()
          emit("observed", load1=load1, max_load1=MAX_LOAD1, stale_age_seconds=STALE_AGE_SECONDS)

          groups = {}
          own_pid = os.getpid()
          for process in read_processes():
              if process["pid"] == own_pid:
                  continue
              groups.setdefault(process["pgid"], []).append(process)

          for pgid, group in sorted(groups.items()):
              matching = [process for process in group if matches_test_workload(process)]
              if not matching:
                  continue

              summary = group_summary(group)
              summary["matching_pids"] = [process["pid"] for process in matching]

              if has_tty(group):
                  emit("skipped_interactive", **summary)
                  continue

              if has_protected_process(group):
                  emit("skipped_protected", **summary)
                  continue

              if summary["oldest_age_seconds"] < STALE_AGE_SECONDS:
                  emit("skipped_young", **summary)
                  continue

              terminate_group(pgid, [process["pid"] for process in group])


      if __name__ == "__main__":
          try:
              main()
          except Exception as exc:
              emit("error", error=str(exc))
              sys.exit(1)
    '';
  };

  lowPrioWrapper = pkgs.writeShellScriptBin "luxnix-test-lowprio" ''
        set -euo pipefail

        if [ "$#" -eq 0 ]; then
          echo "usage: luxnix-test-lowprio <command> [args...]" >&2
          exit 64
        fi

        export NIX_CONFIG="max-jobs = 1''${NIX_CONFIG:+
    $NIX_CONFIG}"
        exec ${pkgs.util-linux}/bin/ionice -c 2 -n 7 ${pkgs.coreutils}/bin/nice -n 10 "$@"
  '';
in
{
  options.luxnix.devOverloadGuard = {
    enable = mkOption {
      type = types.bool;
      default = isDevLaptop;
      description = "Enable the LuxNix developer overload guard for stale detached test processes.";
    };

    staleAgeSeconds = mkOption {
      type = types.ints.positive;
      default = 7200;
      description = "Minimum age in seconds before a detached matching test process group may be terminated.";
    };

    interval = mkOption {
      type = types.str;
      default = "5min";
      description = "systemd timer interval for running the developer overload guard.";
    };

    maxLoad1 = mkOption {
      type = types.float;
      default = 8.0;
      description = "One-minute load threshold included in guard logs for overload context.";
    };

    dryRun = mkOption {
      type = types.bool;
      default = false;
      description = "Log matching stale process groups without terminating them.";
    };

    patterns = mkOption {
      type = types.listOf types.str;
      default = [
        "pytest"
        "py.test"
        "devenv shell -- pytest"
      ];
      description = "Command substrings that identify stale detached developer test workloads.";
    };
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [ lowPrioWrapper ];

    systemd.services.luxnix-dev-overload-guard = {
      description = "LuxNix guard for stale detached developer test process groups";
      serviceConfig = {
        Type = "oneshot";
        User = "root";
        ExecStart = "${guardScript}/bin/luxnix-dev-overload-guard";
        TimeoutStartSec = "30s";
        Nice = 10;
        IOSchedulingClass = "best-effort";
        IOSchedulingPriority = 7;
        CPUQuota = "10%";
      };
    };

    systemd.timers.luxnix-dev-overload-guard = {
      description = "Run the LuxNix developer overload guard regularly";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = cfg.interval;
        OnUnitActiveSec = cfg.interval;
        Unit = "luxnix-dev-overload-guard.service";
      };
    };
  };
}
