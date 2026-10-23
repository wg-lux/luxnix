# LLM configuration

**Schema version:** 1

**Purpose:** Configure one LLM connection for LX-Annotate web, Celery and lx-anonymizer.

## Implementation status

**Runtime options:** implemented

**Shared environment and worker wiring:** implemented

**Validation blocker:** Full host evaluation currently fails at flake.nix:145 with infinite recursion; reported to flake lock owner.

**Option root:** `services.luxnix.lxAnnotateLocal.runtime.llm`

## Options

| Option | Default | Environment variable | Constraints |
| --- | --- | --- | --- |
| `enable` | `true` | `LLM_ENABLED` | Enables inference |
| `provider` | `ollama` | `LLM_PROVIDER` | `ollama` or `vllm` |
| `baseUrl` | http://127.0.0.1:11434 for ollama; http://127.0.0.1:8000 for vllm | `LLM_BASE_URL` | Server root URL |
| `model` | `lx-gemma4-e2b-json` | `LLM_MODEL` | Configured model |
| `timeoutSeconds` | 120 | `LLM_TIMEOUT` | Minimum 1, maximum 120 |
| `caFile` | `null` | `LLM_CA_FILE` | CA file path |
| `clientCertificateFile` | `null` | `LLM_CLIENT_CERT_FILE` | Client certificate path |
| `clientKeyFile` | `null` | `LLM_CLIENT_KEY_FILE` | Private key path |

## Inventory example

```yaml
host_services:
  luxnix.lxAnnotateLocal.runtime.llm.enable: 'true'
  luxnix.lxAnnotateLocal.runtime.llm.provider: '"vllm"'
  luxnix.lxAnnotateLocal.runtime.llm.baseUrl: '"https://llm.internal.example"'
  luxnix.lxAnnotateLocal.runtime.llm.model: '"configured-glm-model"'
  luxnix.lxAnnotateLocal.runtime.llm.caFile: '"/run/secrets/llm-ca"'
  luxnix.lxAnnotateLocal.runtime.llm.clientCertificateFile: '"/run/secrets/llm-client-cert"'
  luxnix.lxAnnotateLocal.runtime.llm.clientKeyFile: '"/run/secrets/llm-client-key"'
```

## Semantics

- Typed runtime.llm settings are authoritative over runtime.extraEnvironment LLM keys.
- Disabled LLM functionality prevents automatic startup of the dedicated LLM worker.
- Only a local default-port Ollama connection adds an Ollama service dependency.
- Enable permits inference; it does not claim that a server or model is ready.
- The application probes the configured model. It does not download or substitute models.
- Use the server root URL without /v1; vllm selects the OpenAI-compatible protocol, including GLM.
- Remote clinical inference requires HTTPS and mTLS; HTTP is limited to literal loopback addresses.
- TLS paths must be readable by the service identity; the private key must remain owner-private.
- Changes require regeneration through Autoconf and the normal deployment workflow, then consumer restarts.
- Inference configuration does not enable training or active learning.
- No host inventories or running services were changed by introducing these options.

## Verification

### Entry 1

#### Command

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD .devenv/state/venv/bin/pytest -q tests/lx-annotate/test_lx_annotate_llm_configuration.py
```

**Result:** 7 passed; covers option defaults, validation and shared web/worker environment for enabled, disabled and remote configurations.

### Entry 2

#### Command

```bash
devenv tasks run docs:check
```

**Result:** passed

### Entry 3

#### Command

```bash
nixfmt --check modules/nixos/services/lx-annotate-local/config.nix modules/nixos/services/lx-annotate-local/scripts/env.nix
```

**Result:** passed; applied Nix files also pass nix-instantiate --parse.

### Entry 4

#### Command

```bash
./feature-tracking/tracker.py validate
```

**Result:** 11 feature definitions valid.

### Entry 5

#### Command

```bash
./feature-tracking/tracker.py check luxnix_host_configuration_cleanup
```

**Result:** passed

### Entry 6

#### Command

```bash
nix eval --json .#nixosConfigurations --apply builtins.attrNames
```

**Result:** blocked by pre-existing concurrent flake.nix recursion at line 145.

### Entry 7

#### Command

```bash
.devenv/state/venv/bin/pyright
```

**Directory:** `/home/admin/lx-anonymizer`

**Result:** 0 errors and 8 existing warnings.

### Entry 8

#### Command

```bash
.devenv/state/venv/bin/pytest -q -o log_cli=false tests/test_config.py tests/test_llm_configuration.py tests/test_llm_meta_helpers.py tests/test_llm_service_vision_ocr.py tests/test_report_reader_init.py
```

**Directory:** `/home/admin/lx-anonymizer`

**Result:** 56 passed.

### Entry 9

#### Command

```bash
uv sync --extra dev
```

**Directory:** `/home/admin/lx-anonymizer`

**Result:** Canceled large dependency downloads; repeated with --frozen and canceled. Tests used the existing virtualenv. Original uv.lock preserved.

### Entry 10

#### Command

```bash
ruff check on existing llm_extractor.py and llm_service.py
```

**Directory:** `/home/admin/lx-anonymizer`

**Result:** Existing lint debt remains; new connection helper and configuration tests pass Ruff.
