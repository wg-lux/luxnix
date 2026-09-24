# Sourced immediately before issuance; never reuse the cached bootstrap token.
# Caller supplies ROLE_ID_FILE and SECRET_ID_FILE. The token stays in this process.
refresh_client_auth() {
  local response auth_error auth_state
  unset VAULT_TOKEN
  if [ ! -s "$ROLE_ID_FILE" ] || [ ! -s "$SECRET_ID_FILE" ]; then
    echo 'ERROR: AppRole enrollment files are unavailable.' >&2
    return 1
  fi
  auth_error="$(umask 077; mktemp)" || return 1
  if ! response="$(jq -n --rawfile role "$ROLE_ID_FILE" --rawfile secret "$SECRET_ID_FILE" \
      '{role_id: ($role | rtrimstr("\n")), secret_id: ($secret | rtrimstr("\n"))}' \
      | vault write -field=token auth/approle/login - 2>"$auth_error")"; then
    auth_state="$("$VAULT_AUTH_ERROR_CLASSIFIER" "$auth_error")" || auth_state=vault-error
    rm -f -- "$auth_error"
    echo "ERROR: fresh Vault AppRole authentication failed (state: $auth_state)." >&2
    case "$auth_state" in
      tls-trust-failed) echo 'Verify the configured Vault CA and server certificate; do not bypass TLS verification.' >&2 ;;
      vault-sealed) echo 'The Vault custodian must unseal the server.' >&2 ;;
      vault-unreachable) echo 'Restore the configured VPN, DNS, and Vault network path.' >&2 ;;
      auth-rejected) echo 'Use the documented site AppRole recovery/rotation workflow; do not reuse another host identity.' >&2 ;;
      *) echo 'Run luxnix-vault-enrollment-status for recovery guidance.' >&2 ;;
    esac
    return 1
  fi
  rm -f -- "$auth_error"
  if [ -z "$response" ]; then
    echo 'ERROR: Vault returned an empty authentication token.' >&2
    return 1
  fi
  export VAULT_TOKEN="$response"
}
