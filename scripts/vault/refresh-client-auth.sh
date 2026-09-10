# Sourced immediately before issuance; never reuse the cached bootstrap token.
# Caller supplies ROLE_ID_FILE and SECRET_ID_FILE. The token stays in this process.
refresh_client_auth() {
  local response
  unset VAULT_TOKEN
  if [ ! -s "$ROLE_ID_FILE" ] || [ ! -s "$SECRET_ID_FILE" ]; then
    echo 'ERROR: AppRole enrollment files are unavailable.' >&2
    return 1
  fi
  if ! response="$(jq -n --rawfile role "$ROLE_ID_FILE" --rawfile secret "$SECRET_ID_FILE" \
      '{role_id: ($role | rtrimstr("\n")), secret_id: ($secret | rtrimstr("\n"))}' \
      | vault write -field=token auth/approle/login - 2>/dev/null)"; then
    echo 'ERROR: fresh Vault AppRole authentication failed.' >&2
    return 1
  fi
  if [ -z "$response" ]; then
    echo 'ERROR: Vault returned an empty authentication token.' >&2
    return 1
  fi
  export VAULT_TOKEN="$response"
}
