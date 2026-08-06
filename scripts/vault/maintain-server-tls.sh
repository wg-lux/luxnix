#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: maintain-server-tls.sh OPTIONS

Required:
  --state-dir PATH
  --ca-cert PATH
  --ca-key PATH
  --server-cert PATH
  --server-key PATH
  --read-group GROUP
  --ca-common-name NAME
  --server-common-name NAME
  --ca-validity-days DAYS
  --leaf-validity-days DAYS
  --renew-before-days DAYS
  --dns-name NAME                 repeatable; at least one required
  --rotation-marker PATH

Optional:
  --ip-address ADDRESS            repeatable
  --force-renew
EOF
}

state_dir=""
ca_cert=""
ca_key=""
server_cert=""
server_key=""
read_group=""
ca_common_name=""
server_common_name=""
ca_validity_days=""
leaf_validity_days=""
renew_before_days=""
rotation_marker=""
force_renew=false
dns_names=()
ip_addresses=()

while (($#)); do
  case "$1" in
    --state-dir) state_dir="${2:?}"; shift 2 ;;
    --ca-cert) ca_cert="${2:?}"; shift 2 ;;
    --ca-key) ca_key="${2:?}"; shift 2 ;;
    --server-cert) server_cert="${2:?}"; shift 2 ;;
    --server-key) server_key="${2:?}"; shift 2 ;;
    --read-group) read_group="${2:?}"; shift 2 ;;
    --ca-common-name) ca_common_name="${2:?}"; shift 2 ;;
    --server-common-name) server_common_name="${2:?}"; shift 2 ;;
    --ca-validity-days) ca_validity_days="${2:?}"; shift 2 ;;
    --leaf-validity-days) leaf_validity_days="${2:?}"; shift 2 ;;
    --renew-before-days) renew_before_days="${2:?}"; shift 2 ;;
    --dns-name) dns_names+=("${2:?}"); shift 2 ;;
    --ip-address) ip_addresses+=("${2:?}"); shift 2 ;;
    --rotation-marker) rotation_marker="${2:?}"; shift 2 ;;
    --force-renew) force_renew=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for required in state_dir ca_cert ca_key server_cert server_key read_group \
  ca_common_name server_common_name ca_validity_days leaf_validity_days \
  renew_before_days rotation_marker; do
  if [[ -z "${!required}" ]]; then
    echo "ERROR: --${required//_/-} is required." >&2
    exit 2
  fi
done
if ((${#dns_names[@]} == 0)); then
  echo "ERROR: at least one --dns-name is required." >&2
  exit 2
fi
for days in "$ca_validity_days" "$leaf_validity_days" "$renew_before_days"; do
  if [[ ! "$days" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: certificate lifetimes must be positive whole days." >&2
    exit 2
  fi
done

install -d -m 0750 "$state_dir"Q  AySXedrw432 A
chgrp "$read_group" "$state_dir"
rm -f "$rotation_marker"

if { [[ -s "$ca_cert" ]] && [[ ! -s "$ca_key" ]]; } \
  || { [[ ! -s "$ca_cert" ]] && [[ -s "$ca_key" ]]; }; then
  echo "ERROR: Vault CA certificate/key pair is incomplete; refusing automatic CA replacement." >&2
  exit 1
fi

if [[ ! -s "$ca_cert" ]]; then
  ca_cert_tmp="$(mktemp "$state_dir/.ca.crt.XXXXXX")"
  ca_key_tmp="$(mktemp "$state_dir/.ca.key.XXXXXX")"
  cleanup_ca() { rm -f "$ca_cert_tmp" "$ca_key_tmp"; }
  trap cleanup_ca EXIT
  openssl req -x509 -newkey ec \
    -pkeyopt ec_paramgen_curve:prime256v1 -sha256 -nodes \
    -days "$ca_validity_days" -subj "/CN=$ca_common_name" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -keyout "$ca_key_tmp" -out "$ca_cert_tmp"
  chmod 0600 "$ca_key_tmp"
  chmod 0644 "$ca_cert_tmp"
  mv -f "$ca_key_tmp" "$ca_key"
  mv -f "$ca_cert_tmp" "$ca_cert"
  trap - EXIT
  echo "Created the stable Vault server CA. Its key will not be rotated automatically."
fi

renew_before_seconds=$((renew_before_days * 24 * 60 * 60))
if ! openssl x509 -in "$ca_cert" -noout -checkend "$renew_before_seconds"; then
  echo "ERROR: Vault CA is near expiry; use the reviewed CA migration procedure. Refusing automatic replacement." >&2
  exit 1
fi
if ! openssl x509 -in "$ca_cert" -noout -text | grep -q 'CA:TRUE'; then
  echo "ERROR: configured Vault trust anchor is not a CA certificate." >&2
  exit 1
fi
ca_public="$(openssl x509 -in "$ca_cert" -pubkey -noout \
  | openssl pkey -pubin -outform DER | sha256sum | cut -d' ' -f1)"
ca_key_public="$(openssl pkey -in "$ca_key" -pubout -outform DER \
  | sha256sum | cut -d' ' -f1)"
if [[ "$ca_public" != "$ca_key_public" ]]; then
  echo "ERROR: Vault CA certificate and private key do not match; refusing automatic CA replacement." >&2
  exit 1
fi

certificate_matches_key() {
  [[ -s "$server_cert" && -s "$server_key" ]] || return 1
  local cert_public key_public
  cert_public="$(openssl x509 -in "$server_cert" -pubkey -noout \
    | openssl pkey -pubin -outform DER | sha256sum | cut -d' ' -f1)" || return 1
  key_public="$(openssl pkey -in "$server_key" -pubout -outform DER \
    | sha256sum | cut -d' ' -f1)" || return 1
  [[ "$cert_public" == "$key_public" ]]
}

leaf_is_current() {
  certificate_matches_key || return 1
  openssl x509 -in "$server_cert" -noout -checkend "$renew_before_seconds" || return 1
  openssl verify -CAfile "$ca_cert" -purpose sslserver "$server_cert" >/dev/null || return 1
  local name address
  for name in "${dns_names[@]}"; do
    openssl x509 -in "$server_cert" -noout -checkhost "$name" >/dev/null || return 1
  done
  for address in "${ip_addresses[@]}"; do
    openssl x509 -in "$server_cert" -noout -checkip "$address" >/dev/null || return 1
  done
}

if [[ "$force_renew" == false ]] && leaf_is_current; then
  exit 0
fi

work_dir="$(mktemp -d "$state_dir/.leaf.XXXXXX")"
cleanup_leaf() { rm -rf -- "$work_dir"; }
trap cleanup_leaf EXIT

subject_alt_names=()
for name in "${dns_names[@]}"; do subject_alt_names+=("DNS:$name"); done
for address in "${ip_addresses[@]}"; do subject_alt_names+=("IP:$address"); done
san_csv="$(IFS=,; printf '%s' "${subject_alt_names[*]}")"
printf '%s\n' \
  '[req]' 'distinguished_name=dn' 'prompt=no' 'req_extensions=req_ext' \
  '[dn]' "CN=$server_common_name" \
  '[req_ext]' 'basicConstraints=critical,CA:FALSE' \
  'keyUsage=critical,digitalSignature' \
  'extendedKeyUsage=serverAuth' "subjectAltName=$san_csv" > "$work_dir/request.cnf"

openssl req -new -newkey ec \
  -pkeyopt ec_paramgen_curve:prime256v1 -sha256 -nodes \
  -config "$work_dir/request.cnf" \
  -keyout "$work_dir/server.key" -out "$work_dir/server.csr"
serial="0x$(openssl rand -hex 16)"
openssl x509 -req -sha256 \
  -in "$work_dir/server.csr" -CA "$ca_cert" -CAkey "$ca_key" \
  -set_serial "$serial" -days "$leaf_validity_days" \
  -extfile "$work_dir/request.cnf" -extensions req_ext \
  -out "$work_dir/server.crt"
openssl verify -CAfile "$ca_cert" -purpose sslserver "$work_dir/server.crt"
chmod 0640 "$work_dir/server.key"
chgrp "$read_group" "$work_dir/server.key"
chmod 0644 "$work_dir/server.crt"
mv -f "$work_dir/server.key" "$server_key"
mv -f "$work_dir/server.crt" "$server_cert"
touch "$rotation_marker"
trap - EXIT
rm -rf -- "$work_dir"
echo "Rotated the Vault server leaf under the unchanged stable CA."
