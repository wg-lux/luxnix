"""Evaluate LLM option types and defaults independently of host deployment."""
import pytest

from nix_eval_helpers import REPO_ROOT, eval_json, eval_result


PRELUDE = f"""
  let
    root = builtins.toPath {str(REPO_ROOT)!r};
    locked = (builtins.fromJSON (builtins.readFile (root + "/flake.lock"))).nodes.nixpkgs.locked;
    lib = import ((builtins.fetchTree locked).outPath + "/lib");
    optionModule = import (root + "/modules/nixos/services/lx-annotate-local/options/runtime.nix") {{
      inherit lib;
      pkgs = {{}};
      cfg = {{}};
      lxAnnotateRuntime = {{ identities = {{}}; paths = {{}}; }};
    }};
  in
""".replace("'", '\"')


@pytest.mark.parametrize("provider,url", [("ollama", "http://127.0.0.1:11434"), ("vllm", "http://127.0.0.1:8000")])
def test_provider_defaults(provider, url):
    result = eval_json(PRELUDE + '''
      let
        system = lib.evalModules {
          modules = [optionModule { services.luxnix.lxAnnotateLocal.runtime.llm.provider = "PROVIDER"; }];
        };
      in system.config.services.luxnix.lxAnnotateLocal.runtime.llm
    '''.replace("PROVIDER", provider))
    assert result["enable"] is True
    assert result["baseUrl"] == url
    assert result["model"] == "lx-gemma4-e2b-json"
    assert result["timeoutSeconds"] == 120


def test_disabled_custom_connection():
    result = eval_json(PRELUDE + '''
      let
        system = lib.evalModules {
          modules = [optionModule { services.luxnix.lxAnnotateLocal.runtime.llm = {
            enable = false;
            provider = "vllm";
            baseUrl = "https://llm.example";
            model = "glm";
            timeoutSeconds = 30;
          }; }];
        };
      in system.config.services.luxnix.lxAnnotateLocal.runtime.llm
    ''')
    assert result["enable"] is False
    assert result["baseUrl"] == "https://llm.example"
    assert result["model"] == "glm"
    assert result["timeoutSeconds"] == 30


def test_invalid_timeout_rejected():
    result = eval_result(PRELUDE + '''
      let
        system = lib.evalModules {
          modules = [optionModule { services.luxnix.lxAnnotateLocal.runtime.llm.timeoutSeconds = 0; }];
        };
      in system.config.services.luxnix.lxAnnotateLocal.runtime.llm.timeoutSeconds
    ''')
    assert result.returncode != 0
    assert "timeoutSeconds" in result.stderr


@pytest.mark.parametrize("enabled,provider,url", [
    (True, "ollama", "http://127.0.0.1:11434"),
    (True, "vllm", "https://llm.example"),
    (False, "ollama", "http://127.0.0.1:11434"),
])
def test_common_and_worker_environment_agree(enabled, provider, url):
    import json

    values = {
        "enable": enabled, "provider": provider, "baseUrl": url,
        "model": "configured-model", "timeoutSeconds": 45,
        "caFile": "/run/secrets/llm-ca",
        "clientCertificateFile": "/run/secrets/llm-cert",
        "clientKeyFile": "/run/secrets/llm-key",
    }
    result = eval_json(PRELUDE + '''
      let
        system = lib.evalModules {
          modules = [optionModule { services.luxnix.lxAnnotateLocal.runtime.llm =
            builtins.fromJSON VALUES;
          }];
        };
        cfg = {
          django = { identitySaltKeyringFile = null; identitySaltFile = null; };
          runtime = system.config.services.luxnix.lxAnnotateLocal.runtime // {
            monitoring.enable = false;
            extraEnvironment = { LLM_ENABLED = "conflicting-legacy-value"; };
          };
          hub = {
            outboundTransfer = {
              clientCertificateFile = null;
              clientKeyFile = null;
              caFile = null;
              sourceNodeSecretFile = null;
              recipientPublicKeyFile = null;
            };
            transferApi.recipientPrivateKeyFiles = [];
          };
        };
        env = import (root + "/modules/nixos/services/lx-annotate-local/scripts/env.nix") {
          inherit lib cfg;
          config = {};
          pkgs = {};
          monitoringConfigFile = "/etc/lx-annotate/monitoring.json";
          lxAnnotateRuntime = { identities = {}; paths = {}; env = {}; };
        };
      in {
        common = lib.getAttrs (builtins.attrNames env.llmEnv) env.commonEnv;
        worker = env.llmInferenceWorkerEnv;
      }
    '''.replace("VALUES", json.dumps(json.dumps(values))))
    expected = {
        "LLM_ENABLED": str(enabled).lower(), "LLM_PROVIDER": provider,
        "LLM_BASE_URL": url, "LLM_MODEL": "configured-model", "LLM_TIMEOUT": "45",
        "LLM_CA_FILE": "/run/secrets/llm-ca", "LLM_CLIENT_CERT_FILE": "/run/secrets/llm-cert",
        "LLM_CLIENT_KEY_FILE": "/run/secrets/llm-key",
    }
    assert result["common"] == expected
    assert result["worker"] == expected | {"REPORT_LLM_JOB_MODE": "celery"}
