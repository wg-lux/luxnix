#!/usr/bin/env bash
set -euo pipefail

echo " Evaluating all NixOS configurations in flake..."
echo ""
echo " What this script does:"
echo " • Iterates over each system defined in nixosConfigurations"
echo " • Evaluates the full system config for each (but does not build or run)"
echo " • Logs any errors to: ./eval-logs/<hostname>-eval.log"
echo " • Continues even if some systems fail"
echo ""
echo " Important:"
echo " • Nix evaluation stops at the FIRST fatal error inside each system"
echo " • To find more errors: fix the first one, then re-run the script"
echo ""


HOSTS=$(nix eval --impure --json --expr \
  'builtins.attrNames (builtins.getFlake (toString ./.)).nixosConfigurations' | jq -r '.[]')

failures=0
LOGDIR="tests/eval-logs"
mkdir -p "$LOGDIR"

for host in $HOSTS; do
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo " Evaluating: $host"

  if output=$(nix eval ".#nixosConfigurations.${host}.config.system.build.toplevel" 2>&1); then
    echo " $host: Evaluation successful"
  else
    echo " $host: Evaluation failed"
    echo "$output" | tee "$LOGDIR/${host}-eval.log"
    failures=$((failures + 1))
  fi
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $failures -gt 0 ]]; then
  echo " $failures system(s) failed evaluation."
  echo " Logs saved to ./$LOGDIR/"
  exit 1
else
  echo " All systems evaluated successfully."
fi
