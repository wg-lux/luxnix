# Resolve only the production closure from the matching application's own lock.
{
  pkgs,
  lib,
  projectSource,
  applicationWheel,
}:
let
  selection =
    pkgs.runCommand "lx-annotate-wheelhouse-selection"
      {
        nativeBuildInputs = [
          pkgs.uv
          (pkgs.python312.withPackages (p: [ p.packaging ]))
        ];
      }
      ''
        export HOME="$TMPDIR" UV_CACHE_DIR="$TMPDIR/uv-cache"
        cp -r ${projectSource} project
        chmod -R u+w project
        python ${./scripts/wheelhouse-lock.py} "$PWD/project" ${applicationWheel} > "$out"
      '';
  lock = builtins.fromJSON (builtins.readFile selection);
  fetch =
    artifact:
    pkgs.fetchurl {
      name = artifact.filename;
      inherit (artifact) url sha256;
    };
  sources = builtins.filter (artifact: artifact.source) lock.artifacts;
  binaries = builtins.filter (artifact: !artifact.source) lock.artifacts;
  builder = pkgs.python312.withPackages (p: [
    p.pip
    p.setuptools
    p.wheel
    p.requests
  ]);
  sourceWheels =
    pkgs.runCommand "lx-annotate-${lock.version}-source-wheels"
      {
        nativeBuildInputs = [ builder ];
      }
      ''
        export HOME="$TMPDIR"
        export PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1
        mkdir -p "$out"
        ${lib.concatMapStringsSep "\n" (artifact: ''
          python -m pip wheel --no-deps --no-build-isolation --no-index \
            --wheel-dir "$out" ${fetch artifact}
        '') sources}
      '';
  wheelhouse =
    pkgs.runCommand "lx-annotate-${lock.version}-locked-wheelhouse"
      {
        nativeBuildInputs = [ builder ];
      }
      ''
        export HOME="$TMPDIR" PIP_DISABLE_PIP_VERSION_CHECK=1
        mkdir -p "$out"
        ln -s ${applicationWheel} "$out/${lock.applicationFilename}"
        ${lib.concatMapStringsSep "\n" (artifact: ''
          ln -s ${fetch artifact} "$out/${artifact.filename}"
        '') binaries}
        for wheel in ${sourceWheels}/*.whl; do
          [ -e "$wheel" ] || continue
          ln -s "$wheel" "$out/$(basename "$wheel")"
        done
        python - "$out" <<'PY'
        import hashlib
        from pathlib import Path
        import sys
        root = Path(sys.argv[1])
        requirements = []
        for wheel in sorted(root.glob("*.whl")):
            name, version = wheel.name.split("-")[:2]
            with wheel.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            requirements.append(f"{name}=={version} --hash=sha256:{digest}\n")
        (root / "requirements.txt").write_text("".join(requirements))
        PY
        python -m pip install --dry-run --ignore-installed --no-index \
          --target "$TMPDIR/install-check" \
          --find-links "$out" --require-hashes --only-binary=:all: \
          --requirement "$out/requirements.txt"
      '';
in
{
  inherit lock sourceWheels wheelhouse;
}
