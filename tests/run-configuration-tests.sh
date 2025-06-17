#!/usr/bin/env bash
set -euo pipefail

echo " Evaluating and building all NixOS configurations in flake..."
echo ""
echo " What this script does:"
echo " • Iterates over each system defined in nixosConfigurations"
echo " • Evaluates the full system config for each (does not apply)"
echo " • Builds the system config (does not activate it)"
echo " • Logs all errors to: ./tests/eval-logs/<host>-eval.log and <host>-build.log"
echo " • Continues even if some systems fail"
echo ""
echo "  Important:"
echo " • Nix evaluation stops at the FIRST fatal error inside each system"
echo " • To find more errors: fix the first one, then re-run the script"
echo ""

# List all NixOS configuration hosts
HOSTS=$(nix eval --impure --json --expr \
  'builtins.attrNames (builtins.getFlake (toString ./.)).nixosConfigurations' | jq -r '.[]')

failures=0
LOGDIR="tests/eval-logs"
mkdir -p "$LOGDIR"

BUILD_TIMEOUT=80  # seconds

for host in $HOSTS; do
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo " Evaluating: $host"

  eval_log="$LOGDIR/${host}-eval.log"
  build_log="$LOGDIR/${host}-build.log"
  temp_log="$(mktemp)"

  # Step 1: Evaluation
  if nix eval ".#nixosConfigurations.${host}.config.system.build.toplevel" --show-trace > /dev/null 2> "$eval_log"; then
    echo " $host: Evaluation successful"
  else
    echo " $host: Evaluation failed"
    cat "$eval_log"
    failures=$((failures + 1))
    continue
  fi

  # Step 2: Build with timeout
  echo " Building: $host (timeout in ${BUILD_TIMEOUT}s)"
  build_cmd="nix build .#nixosConfigurations.${host}.config.system.build.toplevel --no-link"

  if timeout "$BUILD_TIMEOUT" bash -c "$build_cmd" > "$temp_log" 2>&1; then
    echo " $host: Build successful"
  else
    exit_code=$?
    cp "$temp_log" "$build_log"

    if [[ $exit_code -eq 124 ]]; then
      echo "  $host: Build timed out after ${BUILD_TIMEOUT}s" | tee -a "$build_log"
      echo "  Possible reasons: large derivation, missing cache, network issue" | tee -a "$build_log"
    else
      echo " $host: Build failed" | tee -a "$build_log"
    fi

    echo " Last 20 lines of build output:" | tee -a "$build_log"
    tail -n 20 "$build_log" | tee -a "$build_log"

    echo ""
    echo "  To manually debug:"
    echo "   less $build_log"
    echo "   nix build .#nixosConfigurations.${host}.config.system.build.toplevel --no-link --verbose"

    failures=$((failures + 1))
  fi
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $failures -gt 0 ]]; then
  echo " $failures system(s) failed evaluation or build."
  echo " Logs saved to: ./$LOGDIR/"
  exit 1
else
  echo " All systems evaluated and built successfully."
fi
