"""One switch selects the hub secrets server; client contracts stay identical."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def evaluate(body):
    expression = f'''let
      f = builtins.getFlake "git+file://{ROOT}";
      lib = f.inputs.nixpkgs.lib;
      extend = host: modules: (f.nixosConfigurations.${{host}}.extendModules {{ inherit modules; }}).config;
      openbao = {{ luxnix.vault.backend = "openbao"; }};
      failed = c: map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
    in {body}'''
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=900,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def hub():
    return evaluate('''let
      inspect = c: {
        failed = failed c;
        program = c.luxnix.vault.clientPackage.name;
        unit = c.luxnix.vault.serverUnit;
        storage = c.luxnix.vault.serverStoragePath;
        vault = c.services.vault.enable;
        openbao = c.services.openbao.enable;
        guarded = builtins.attrNames c.luxnix.storage.operatorUnlocked.guardedServices;
        caPublisher = c.systemd.services.luxnix-vault-publish-hub-client-ca.requires;
        tlsRequiredBy = c.systemd.services.luxnix-vault-managed-server-tls.requiredBy;
        tools = builtins.filter (lib.hasPrefix "luxnix-vault-")
          (map (p: p.name or "") c.environment.systemPackages);
      };
      bao = extend "gs-02" [ openbao {
        fileSystems."/var/lib/openbao" = { device = "/dev/mapper/test"; fsType = "ext4"; };
      } ];
      unmounted = extend "gs-02" [ openbao ];
    in {
      vault = inspect f.nixosConfigurations.gs-02.config;
      openbao = inspect bao // {
        listener = bao.services.openbao.settings.listener.release;
        api = bao.services.openbao.settings.api_addr;
        vaultApi = bao.luxnix.vault.server.apiAddress;
        credentials = bao.systemd.services.openbao.serviceConfig.LoadCredential;
        restart = bao.systemd.services.openbao.serviceConfig.Restart;
        groups = bao.users.users.openbao.extraGroups;
        sensitive = bao.luxnix.generic-settings.sensitiveServiceGroupName;
        tls = { inherit (bao.luxnix.vault.server) tlsCertFile tlsKeyFile; };
      };
      unmounted = failed unmounted;
    }''')


def test_default_backend_is_unchanged_vault(hub):
    vault = hub["vault"]
    assert vault["failed"] == []
    assert (vault["vault"], vault["openbao"]) == (True, False)
    assert (vault["unit"], vault["storage"]) == ("vault.service", "/var/lib/vault")
    assert vault["program"].startswith("vault-")
    assert "vault" in vault["guarded"] and "openbao" not in vault["guarded"]


def test_openbao_backend_replaces_the_server_and_keeps_its_contract(hub):
    bao = hub["openbao"]
    assert bao["failed"] == []
    assert (bao["vault"], bao["openbao"]) == (False, True)
    # Separate state: OpenBao never opens the Vault Raft directory.
    assert (bao["unit"], bao["storage"]) == ("openbao.service", "/var/lib/openbao")
    assert bao["program"] == "luxnix-openbao-vault-cli"
    assert "openbao" in bao["guarded"] and "vault" not in bao["guarded"]
    assert bao["caPublisher"] == ["openbao.service"]
    assert "openbao.service" in bao["tlsRequiredBy"]
    assert bao["api"] == bao["vaultApi"]
    # A renewed leaf must be reloadable by SIGHUP: a restart would seal the hub.
    assert bao["credentials"] == []
    assert bao["listener"]["tls_cert_file"] == bao["tls"]["tlsCertFile"]
    assert bao["listener"]["tls_key_file"] == bao["tls"]["tlsKeyFile"]
    assert bao["listener"]["tls_disable"] is False
    assert bao["restart"] == "always"
    assert bao["sensitive"] in bao["groups"]
    assert set(bao["tools"]) == set(hub["vault"]["tools"])
    assert {"luxnix-vault-publish-secret", "luxnix-vault-issue-site-token"} <= set(bao["tools"])


def test_openbao_hub_requires_its_own_encrypted_mount(hub):
    assert any("/var/lib/openbao" in message for message in hub["unmounted"])


@pytest.fixture(scope="module")
def site():
    return evaluate('''let
      secrets = { luxnix.vault.client.secrets = {
        smtp_password.restartUnits = [ "nginx.service" ];
        host_key = { scope = "host"; required = false; stripNewlines = false; mode = "0600"; };
      }; };
      inspect = c: let unit = c.systemd.services.luxnix-hub-secrets; in {
        failed = failed c;
        script = builtins.readFile unit.serviceConfig.ExecStart;
        inherit (unit) before wantedBy;
        remain = unit.serviceConfig.RemainAfterExit or false;
        timer = c.systemd.timers.luxnix-hub-secrets.timerConfig;
        guarded = c.luxnix.storage.operatorUnlocked.guardedServices ? luxnix-hub-secrets;
        offline = c.luxnix.vault.client.allowOffline;
        keycloak = (c.roles.managed-secrets.customSecrets.lx_hub_source_node_secret or { generator = ""; }).generator;
      };
      token = extend "gc-10" [ openbao secrets ({ lib, ... }: {
        luxnix.vault.client.hubSite = { enable = true; auth = "token"; };
        luxnix.vault.client.auth = {
          method = lib.mkForce "tokenFile";
          roleIdFile = lib.mkForce null;
          secretIdFile = lib.mkForce null;
        };
      }) ];
    in {
      approle = inspect (extend "gc-10" [ openbao secrets ]);
      token = inspect token // { inherit (token.luxnix.vault.client.auth) tokenFile; tools =
        map (p: p.name or "") token.environment.systemPackages; };
      none = f.nixosConfigurations.gc-10.config.systemd.services ? luxnix-hub-secrets;
      unauthenticated = failed (extend "gs-02" [ secrets ]);
    }''')


def test_declared_secrets_are_fetched_with_a_fresh_scoped_token(site):
    approle = site["approle"]
    assert approle["failed"] == []
    script = approle["script"]
    assert "refresh_client_auth" in script and "unset VAULT_SKIP_VERIFY" in script
    assert "luxnix-openbao-vault-cli/bin/vault" in script
    assert (
        "deliver smtp_password lx-hub-secrets/shared/smtp_password value "
        "/etc/secrets/vault/hub/smtp_password root sensitiveServices 0640 1 1 nginx.service"
    ) in script
    assert (
        "deliver host_key lx-hub-secrets/hosts/gc-10.intern/host_key value "
        "/etc/secrets/vault/hub/host_key root sensitiveServices 0600 0 0"
    ) in script
    # Outage tolerance follows the existing allowOffline switch of this host.
    assert ("--tolerate-outage" in script) is approle["offline"]
    assert "--tolerate-outage" in approle["keycloak"] or not approle["offline"]


def test_refresh_never_restarts_consumers_unless_a_value_changed(site):
    approle = site["approle"]
    assert approle["remain"] is False
    assert approle["before"] == ["nginx.service"]
    assert "systemctl try-restart --no-block" in approle["script"]
    assert approle["timer"]["OnUnitInactiveSec"] == "15min"
    assert approle["guarded"] is True
    assert site["none"] is False


def test_token_based_host_uses_and_renews_its_site_token(site):
    token = site["token"]
    assert token["failed"] == []
    assert token["tokenFile"] == "/etc/secrets/vault/hub-pki/site-token"
    assert "vault token renew" in token["script"]
    assert "refresh_client_auth" not in token["script"]
    assert "luxnix-vault-install-site-token" in token["tools"]


def test_declared_secrets_need_hub_authentication(site):
    assert any("luxnix.vault.client.secrets requires" in m for m in site["unauthenticated"])


def test_site_policy_grants_only_shared_and_own_host_paths():
    source = (ROOT / "modules/nixos/luxnix/vault/tools/hub-sites.nix").read_text()
    policy = source.split('policy_file="$(${pkgs.coreutils}/bin/mktemp)"', 1)[1].split(
        "vault policy write", 1
    )[0]
    assert '$kv_mount/data/shared/*' in policy
    assert '$kv_mount/data/hosts/$node_fqdn/*' in policy
    assert "hosts/*" not in policy.replace("hosts/$node_fqdn/*", "")
    # Every KV grant is read-only; the only other read is the public client CA.
    assert policy.count('capabilities = ["read"]') == policy.count('$kv_mount/data/') + 1
    assert '$mount/cert/ca' in policy
