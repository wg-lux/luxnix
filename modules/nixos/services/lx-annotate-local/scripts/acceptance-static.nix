# Shared bounded HTTPS probe for the deployed Vite entry-point manifest.
{
  pkgs,
  lib,
  hostname,
  certificatePath,
}:
''
  if ! (
    set -o pipefail
    ${pkgs.curl}/bin/curl --fail --silent --show-error \
      --connect-timeout 5 --max-time 15 --max-filesize 1048576 \
      --cacert ${lib.escapeShellArg certificatePath} \
      --resolve ${lib.escapeShellArg "${hostname}:443:127.0.0.1"} \
      ${lib.escapeShellArg "https://${hostname}/static/.vite/manifest.json"} \
      | ${pkgs.jq}/bin/jq --slurp --exit-status '
          length == 1
          and (.[0] | type == "object")
          and (.[0]["src/main.ts"] | type == "object")
          and (.[0]["src/main.ts"].file | type == "string" and length > 0)
        ' >/dev/null 2>/dev/null
  ); then
    echo "ERROR: TLS static manifest probe failed or returned an invalid entry-point manifest." >&2
    exit 1
  fi
''
