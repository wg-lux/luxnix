# Build and inspect ExecStart binaries without running any service or Django command.
{
  host ? "gc-02",
}:
let
  flake = builtins.getFlake ("git+file://" + toString ../..);
  inherit (flake.inputs.nixpkgs) lib;
  machine = flake.nixosConfigurations.${host};
  services = lib.filterAttrs (
    name: _: lib.hasPrefix "lx-annotate" name
  ) machine.config.systemd.services;
  commands = lib.mapAttrs (_: service: service.serviceConfig.ExecStart or "") services;
  manifest = machine.pkgs.writeText "lx-annotate-service-commands.json" (builtins.toJSON commands);
in
machine.pkgs.runCommand "lx-annotate-service-binaries-${host}" { } ''
  ${machine.pkgs.python3}/bin/python - ${manifest} <<'PY'
  import json
  import os
  import shlex
  import sys

  commands = json.load(open(sys.argv[1]))
  if not commands:
      raise SystemExit("No lx-annotate services configured for this host")
  for name, command in commands.items():
      binary = shlex.split(command)[0]
      if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
          raise SystemExit(f"Missing executable: {name}: {binary}")
  print(f"Verified {len(commands)} lx-annotate service executables")
  PY
  touch "$out"
''
