{ pkgs, ... }:
{
  alignEnvFileScript = pkgs.writeText "lx-annotate-align-env.py" ''
    import os
    from pathlib import Path

    env_path = Path(os.environ["LX_ANNOTATE_ENV_FILE"])
    desired_module = os.environ["DESIRED_SETTINGS_MODULE"]
    desired_env = os.environ["DESIRED_ENVIRONMENT"]

    if not env_path.exists():
        raise SystemExit(0)

    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = []
    have_module = False
    have_env = False

    for line in lines:
        if line.startswith("DJANGO_SETTINGS_MODULE="):
            updated.append(f"DJANGO_SETTINGS_MODULE={desired_module}")
            have_module = True
        elif line.startswith("DJANGO_ENV="):
            updated.append(f"DJANGO_ENV={desired_env}")
            have_env = True
        else:
            updated.append(line)

    if not have_module:
        updated.append(f"DJANGO_SETTINGS_MODULE={desired_module}")

    if not have_env:
        updated.append(f"DJANGO_ENV={desired_env}")

    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
  '';

  viteManifestEntryScript = pkgs.writeText "lx-annotate-vite-manifest-entry.py" ''
    import json
    import sys

    manifest_path = sys.argv[1]
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        raise SystemExit(1)

    entry = data.get("src/main.ts", {}).get("file")
    if entry:
        print(entry)
        raise SystemExit(0)

    for value in data.values():
        if isinstance(value, dict):
            file_value = value.get("file")
            if file_value:
                print(file_value)
                raise SystemExit(0)

    raise SystemExit(1)
  '';
}
