from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

from lx_administration.yaml import load_unique_yaml_file

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "devenv/commands.yml"
SCRIPT_DEFINITION_PATHS = [
    REPO_ROOT / "devenv/scripts.nix",
    REPO_ROOT / "devenv/management.nix",
]
TASK_DEFINITION_PATHS = [
    REPO_ROOT / "devenv/tasks.nix",
    REPO_ROOT / "devenv/management.nix",
]


def _yaml_mapping(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], load_unique_yaml_file(path))


def _catalog() -> dict[str, Any]:
    return _yaml_mapping(CATALOG_PATH)


def test_every_devenv_wrapper_is_cataloged_once() -> None:
    catalog = _catalog()
    commands = catalog["commands"]
    catalog_ids = [command["id"] for command in commands]
    script_definitions = "\n".join(
        path.read_text(encoding="utf-8") for path in SCRIPT_DEFINITION_PATHS
    )
    defined_ids = set(
        re.findall(r"^\s*([a-z][a-z0-9-]*)\.exec\s*=", script_definitions, re.MULTILINE)
    )
    packaged_ids = set(
        re.findall(
            r"^\s*([a-z][a-z0-9-]*)\.package\s*=",
            script_definitions,
            re.MULTILINE,
        )
    )

    assert len(catalog_ids) == len(set(catalog_ids)), "duplicate command catalog IDs"
    assert set(catalog_ids) == defined_ids
    assert packaged_ids == defined_ids, "every wrapper must declare its shell package"


def test_every_devenv_task_is_cataloged_once() -> None:
    catalog = _catalog()
    project_map = _yaml_mapping(REPO_ROOT / "luxnix.yml")
    risk_levels = project_map["risk_levels"]
    tasks = catalog["tasks"]
    catalog_ids = [task["id"] for task in tasks]
    task_definitions = "\n".join(
        path.read_text(encoding="utf-8") for path in TASK_DEFINITION_PATHS
    )
    defined_ids = set(
        re.findall(
            r'^\s*"([a-z][a-z0-9-]*:[a-z][a-z0-9-]*)"\s*=\s*\{',
            task_definitions,
            re.MULTILINE,
        )
    )

    assert len(catalog_ids) == len(set(catalog_ids)), "duplicate task catalog IDs"
    assert set(catalog_ids) == defined_ids

    for task in tasks:
        assert task["usage"] == f"devenv tasks run {task['id']}"
        assert task["risk"] in risk_levels
        assert isinstance(task["operator_confirmation_required"], bool)
        assert task["summary"].strip()
        assert (REPO_ROOT / task["implementation"]).exists()
        documentation = REPO_ROOT / task["documentation"]
        assert documentation.is_file()
        assert f"devenv tasks run {task['id']}" in documentation.read_text(
            encoding="utf-8"
        )


def test_devenv_catalog_has_actionable_risk_metadata() -> None:
    catalog = _catalog()
    project_map = _yaml_mapping(REPO_ROOT / "luxnix.yml")
    risk_levels = project_map["risk_levels"]

    assert catalog["risk_levels_source"] == "../luxnix.yml#risk_levels"
    assert catalog["task_invocation"] == "devenv tasks run <task> [arguments...]"

    for command in catalog["commands"]:
        command_id = command["id"]
        assert command["risk"] in risk_levels
        assert isinstance(command["operator_confirmation_required"], bool)
        assert command["summary"].strip()
        assert command["usage"].startswith(f"devenv shell {command_id}")
        assert command.get(
            "implementation"
        ), f"{command_id}: implementation path is required"

        for path_field in ("implementation", "documentation"):
            relative_path = command[path_field]
            assert (
                REPO_ROOT / relative_path
            ).exists(), f"{command_id}: missing {path_field} {relative_path}"

        documentation = REPO_ROOT / command["documentation"]
        assert f"devenv shell {command_id}" in documentation.read_text(
            encoding="utf-8"
        )

    tasks_by_id = {task["id"]: task for task in catalog["tasks"]}
    for task_id in (
        "initialize-environment:endoreg-db",
        "autoconf:initialize-vault",
        "endoreg-db:init",
        "endoreg-db:migrate",
    ):
        assert tasks_by_id[task_id]["operator_confirmation_required"] is True


def test_catalog_aliases_resolve_to_cataloged_tasks() -> None:
    catalog = _catalog()
    scripts = (REPO_ROOT / "devenv/scripts.nix").read_text(encoding="utf-8")
    task_ids = {task["id"] for task in catalog["tasks"]}
    aliases = {
        command["id"]: command["alias_for"]
        for command in catalog["commands"]
        if "alias_for" in command
    }

    assert aliases == {"bnsc": "autoconf:generate"}
    assert set(aliases.values()) <= task_ids
    for alias, task_id in aliases.items():
        assert f'{alias}.exec = "devenv tasks run {task_id}";' in scripts


def test_devenv_exposes_separate_refresh_and_report_tasks() -> None:
    tasks = (REPO_ROOT / "devenv/tasks.nix").read_text()
    project = (REPO_ROOT / "pyproject.toml").read_text()
    project_map = _yaml_mapping(REPO_ROOT / "luxnix.yml")
    workflows = {item["id"]: item for item in project_map["workflows"]}

    assert '"autoconf:refresh-facts"' in tasks
    assert '"autoconf:refresh-facts-strict"' in tasks
    assert '"autoconf:generate-report"' in tasks
    assert '"autoconf:generate-hostinfo"' not in tasks
    assert "last-known-good data for failed hosts" in tasks
    assert "private, redacted HTML inventory report" in tasks
    assert "generate-cmdb-report.py" in tasks
    assert "${pkgs.uv}/bin/uv run python scripts/generate-cmdb-report.py" in tasks
    assert '"ansible-cmdb' not in project
    assert workflows["refresh-autoconf-facts"]["risk"] == "remote-read-only"
    assert workflows["refresh-autoconf-facts"]["strict_command"].endswith(
        "autoconf:refresh-facts-strict"
    )
    assert workflows["generate-inventory-report"]["risk"] == "local-state"


def test_bnsc_runs_the_single_canonical_generation_task() -> None:
    tasks = (REPO_ROOT / "devenv/tasks.nix").read_text()
    scripts = (REPO_ROOT / "devenv/scripts.nix").read_text()
    documented_workflow = (REPO_ROOT / "docs/autoconf.md").read_text()

    assert '"autoconf:generate"' in tasks
    assert 'after = [ "autoconf:check" ];' in tasks
    assert 'bnsc.exec = "devenv tasks run autoconf:generate";' in scripts
    assert "devenv shell bnsc" in documented_workflow
    assert tasks.count("scripts/autoconf-pipeline.py") == 2
    assert "scripts/autoconf-pipeline.py" not in scripts
    assert "autoconf:finished" not in tasks
    assert "autoconf:build-nix-system-configs" not in tasks
    assert "ac.package" not in scripts
    assert "ac.exec" not in scripts

    workflow_sources = [
        REPO_ROOT / "luxnix.yml",
        REPO_ROOT / "LxCheatsheet.md",
        REPO_ROOT / "CommonErrors.md",
        REPO_ROOT / "docs/getting-started.md",
        REPO_ROOT / "docs/deployment-guide.md",
        REPO_ROOT / "docs/vault-hub-machine-enrollment.md",
        REPO_ROOT / "conf/nix-templates/readme.md",
    ]
    for source in workflow_sources:
        source_text = source.read_text()
        assert "autoconf:finished" not in source_text
        assert "autoconf:build-nix-system-configs" not in source_text


def test_devenv_scripts_keep_canonical_entry_points_only() -> None:
    scripts = (REPO_ROOT / "devenv/scripts.nix").read_text()
    gitignore = (REPO_ROOT / ".gitignore").read_text()

    assert "bnsc.exec" in scripts
    assert "vault-bootstrap.exec" in scripts
    assert scripts.count("scripts/bootstrap-lx-vault.py") == 1
    assert not (REPO_ROOT / "scripts/lxv-postgres-secrets.py").exists()
    for obsolete_name in (
        "hello.",
        "utest.",
        "blxv.",
        "create-ed25519-keypair.",
        "ensure-ansible-config.",
        "initialize-luxnix-repo.",
    ):
        assert obsolete_name not in scripts
    assert not (REPO_ROOT / "hello.py").exists()
    assert ".repo_initialized" not in gitignore


def test_ansible_guide_explains_remote_mutation_scope() -> None:
    guide_path = REPO_ROOT / "ansible/playbooks/readme.md"
    guide = guide_path.read_text(encoding="utf-8")

    assert "the wrappers themselves do not display a confirmation prompt" in guide
    assert "Both wrappers refuse to run without" in guide
    assert "--limit <host-or-group>" in guide
    assert "--limit all" in guide
    assert "Ansible check mode" in guide
    assert "../inventory/group_vars/README.md" in guide
    assert (guide_path.parent / "../inventory/group_vars/README.md").is_file()


def test_manage_help_points_to_complete_machine_readable_catalogs() -> None:
    management = (REPO_ROOT / "devenv/management.nix").read_text(encoding="utf-8")

    help_body = management.split('"help")', 1)[1].split(";;", 1)[0]
    assert "devenv/commands.yml" in help_body
    assert "luxnix.yml" in help_body
    assert "usage" in help_body.lower()
    assert "risk" in help_body.lower()


def test_ansible_wrappers_forward_arguments_through_uv() -> None:
    catalog = _catalog()
    scripts = (REPO_ROOT / "devenv/scripts.nix").read_text(encoding="utf-8")
    commands = {command["id"]: command for command in catalog["commands"]}

    for command_id in ("run-ansible", "sync-secrets"):
        command = commands[command_id]
        playbook = command["playbook"]
        definition = re.search(
            rf"^\s*{command_id}\.exec\s*=\s*(.*?);$",
            scripts,
            re.MULTILINE | re.DOTALL,
        )
        assert definition, f"missing {command_id} wrapper"
        assert command["implementation"] == "scripts/run-ansible-playbook.sh"
        assert (REPO_ROOT / playbook).is_file()
        assert "LUXNIX_UV_BIN=${pkgs.uv}/bin/uv" in definition.group(1)
        assert "bash scripts/run-ansible-playbook.sh" in definition.group(1)
        assert playbook in definition.group(1)
        assert '"$@"' in definition.group(1)


def test_ansible_runner_rejects_missing_or_empty_limits(tmp_path) -> None:
    runner = REPO_ROOT / "scripts/run-ansible-playbook.sh"
    fake_uv = tmp_path / "uv"
    capture_file = tmp_path / "arguments"
    fake_uv.write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > "$CAPTURE_FILE"\n',
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    environment = os.environ | {
        "CAPTURE_FILE": str(capture_file),
        "LUXNIX_UV_BIN": str(fake_uv),
    }

    for arguments in (
        ["--check", "--diff"],
        ["--limit"],
        ["--limit="],
        ["-l", "--check"],
    ):
        result = subprocess.run(
            ["bash", runner, "ansible/site.yml", *arguments],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

        assert result.returncode == 2
        assert "ERROR:" in result.stderr
        assert not capture_file.exists()


def test_ansible_runner_forwards_supported_limit_forms_and_exit_status(
    tmp_path,
) -> None:
    runner = REPO_ROOT / "scripts/run-ansible-playbook.sh"
    fake_uv = tmp_path / "uv"
    capture_file = tmp_path / "arguments"
    fake_uv.write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > "$CAPTURE_FILE"\nexit 17\n',
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    environment = os.environ | {
        "CAPTURE_FILE": str(capture_file),
        "LUXNIX_UV_BIN": str(fake_uv),
    }

    for limit_arguments in (
        ["--limit", "gc-02"],
        ["--limit=gc-02"],
        ["-l", "gc-02"],
        ["-lgc-02"],
    ):
        result = subprocess.run(
            [
                "bash",
                runner,
                "ansible/site.yml",
                "--check",
                *limit_arguments,
                "--diff",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

        assert result.returncode == 17
        forwarded = capture_file.read_text(encoding="utf-8").splitlines()
        assert forwarded[:3] == ["run", "ansible-playbook", "ansible/site.yml"]
        assert forwarded[3:] == ["--check", *limit_arguments, "--diff"]


def test_connectivity_check_requires_an_explicit_target() -> None:
    script = REPO_ROOT / "scripts/check-connectivity.sh"

    missing_target = subprocess.run(
        ["bash", script],
        capture_output=True,
        text=True,
        check=False,
    )
    help_result = subprocess.run(
        ["bash", script, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert missing_target.returncode == 2
    assert "refusing to default to all" in missing_target.stderr
    assert help_result.returncode == 0
    assert "<inventory-host-or-group>" in help_result.stdout


def test_connectivity_logs_are_private_and_do_not_record_forwarded_arguments() -> None:
    script = (REPO_ROOT / "scripts/check-connectivity.sh").read_text(encoding="utf-8")

    assert "umask 077" in script
    assert 'install -d -m 0700 "${logs_dir}"' in script
    assert "Connectivity check target:" in script
    assert "cmd[*]" not in script


def test_connectivity_check_forwards_arguments_and_creates_private_logs(
    tmp_path,
) -> None:
    repo = tmp_path / "repo"
    script_dir = repo / "scripts"
    config_dir = repo / "conf"
    inventory_dir = repo / "ansible/inventory"
    playbook_dir = repo / "ansible/playbooks"
    fake_bin = tmp_path / "bin"
    for directory in (script_dir, config_dir, inventory_dir, playbook_dir, fake_bin):
        directory.mkdir(parents=True, exist_ok=True)

    script = script_dir / "check-connectivity.sh"
    shutil.copy2(REPO_ROOT / "scripts/check-connectivity.sh", script)
    shutil.copy2(
        REPO_ROOT / "conf/connectivity-ansible.cfg",
        config_dir / "connectivity-ansible.cfg",
    )
    (inventory_dir / "hosts.ini").write_text("[all]\nnode-01\n", encoding="utf-8")
    (playbook_dir / "connectivity-check.yml").write_text("---\n", encoding="utf-8")

    capture_file = tmp_path / "ansible-arguments"
    fake_ansible = fake_bin / "ansible-playbook"
    fake_ansible.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$@" > "$CAPTURE_FILE"
echo "fake connectivity ok"
""",
        encoding="utf-8",
    )
    fake_ansible.chmod(0o755)

    result = subprocess.run(
        ["bash", script, "node-01", "--check", "--diff"],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ
        | {
            "CAPTURE_FILE": str(capture_file),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
        },
    )

    assert result.returncode == 0, result.stderr
    arguments = capture_file.read_text(encoding="utf-8").splitlines()
    assert arguments[-4:] == ["--limit", "node-01", "--check", "--diff"]

    logs_dir = repo / "logs"
    logs = list(logs_dir.glob("connectivity-*.log"))
    assert logs_dir.stat().st_mode & 0o777 == 0o700
    assert len(logs) == 1
    assert logs[0].stat().st_mode & 0o777 == 0o600
    log_text = logs[0].read_text(encoding="utf-8")
    assert "Connectivity check target: node-01" in log_text
    assert "fake connectivity ok" in log_text
    assert "--check" not in log_text
    assert "--diff" not in log_text


def test_streamable_migration_requires_a_host_before_migration_options() -> None:
    script = REPO_ROOT / "scripts/lx-annotate-streamable-migration.sh"

    missing_host = subprocess.run(
        ["bash", script], capture_output=True, text=True, check=False
    )
    help_result = subprocess.run(
        ["bash", script, "--help"], capture_output=True, text=True, check=False
    )
    option_as_host = subprocess.run(
        ["bash", script, "--dry-run"], capture_output=True, text=True, check=False
    )

    assert missing_host.returncode == 2
    assert "target host is required" in missing_host.stderr
    assert help_result.returncode == 0
    assert "<host>" in help_result.stdout
    assert option_as_host.returncode == 2
    assert "not a migration option" in option_as_host.stderr


def test_streamable_migration_executes_only_the_deployed_system_command() -> None:
    script = (REPO_ROOT / "scripts/lx-annotate-streamable-migration.sh").read_text(
        encoding="utf-8"
    )

    assert "exec ssh -t" in script
    assert (
        "/run/current-system/sw/bin/lx-annotate-migrate-video-streamable-storage"
        in script
    )
    assert "/nix/store/" not in script
    assert ".venv/" not in script


def test_streamable_migration_forwards_arguments_and_ssh_exit_status(tmp_path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture_file = tmp_path / "ssh-arguments"
    fake_ssh = fake_bin / "ssh"
    fake_ssh.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$@" > "$CAPTURE_FILE"
exit 17
""",
        encoding="utf-8",
    )
    fake_ssh.chmod(0o755)

    result = subprocess.run(
        [
            "bash",
            REPO_ROOT / "scripts/lx-annotate-streamable-migration.sh",
            "gc-10",
            "--dry-run",
            "--processed-only",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ
        | {
            "CAPTURE_FILE": str(capture_file),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
        },
    )

    assert result.returncode == 17
    arguments = capture_file.read_text(encoding="utf-8").splitlines()
    assert arguments[:2] == ["-t", "gc-10"]
    assert arguments[-3:] == [
        "lx-annotate-streamable-migration",
        "--dry-run",
        "--processed-only",
    ]


def test_devenv_examples_use_the_supported_cli_form() -> None:
    example_files = [
        REPO_ROOT / "ansible/admin-passwords.example.yml",
        CATALOG_PATH,
        REPO_ROOT / "luxnix.yml",
    ]

    stale = [
        str(path.relative_to(REPO_ROOT))
        for path in example_files
        if "devenv run " in path.read_text(encoding="utf-8")
    ]
    assert not stale
    assert "development_command_catalog: devenv/commands.yml" in (
        REPO_ROOT / "luxnix.yml"
    ).read_text(encoding="utf-8")


def test_every_documented_devenv_task_reference_resolves() -> None:
    task_sources = {
        path: path.read_text(encoding="utf-8") for path in TASK_DEFINITION_PATHS
    }
    defined_tasks = {
        task_id
        for source in task_sources.values()
        for task_id in re.findall(
            r'^\s*"([a-z][a-z0-9-]*:[a-z][a-z0-9-]*)"\s*=',
            source,
            re.MULTILINE,
        )
    }
    reference_paths = [
        *REPO_ROOT.glob("devenv/*.nix"),
        REPO_ROOT / "README.md",
        REPO_ROOT / "CommonErrors.md",
        REPO_ROOT / "LxCheatsheet.md",
        REPO_ROOT / "luxnix.yml",
        REPO_ROOT / "conf/nix-templates/readme.md",
        *REPO_ROOT.glob("docs/*.md"),
    ]
    unresolved = {
        f"{path.relative_to(REPO_ROOT)}: {task_id}"
        for path in reference_paths
        for task_id in re.findall(
            r"\bdevenv tasks run ([a-z][a-z0-9-]*:[a-z][a-z0-9-]*)",
            path.read_text(encoding="utf-8"),
        )
        if task_id not in defined_tasks
    }

    assert defined_tasks
    assert not unresolved, "unresolved Devenv task references:\n" + "\n".join(
        sorted(unresolved)
    )


def test_devenv_composition_passes_only_required_inputs() -> None:
    root_config = (REPO_ROOT / "devenv.nix").read_text(encoding="utf-8")
    composition_files = [
        REPO_ROOT / "devenv/default.nix",
        REPO_ROOT / "devenv/management.nix",
        REPO_ROOT / "devenv/processes.nix",
    ]
    composition = "\n".join(
        path.read_text(encoding="utf-8") for path in composition_files
    )

    assert "isDev" not in root_config
    assert "isDev" not in composition
    assert "baseBuildInputs" not in root_config
    assert "inputs," not in root_config
    assert "devenv_utils" not in root_config
    assert "devenvUtils" in root_config


def test_devenv_has_one_package_list_and_one_python_toolchain():
    packages = (REPO_ROOT / "devenv/packages.nix").read_text()
    devenv_config = (REPO_ROOT / "devenv.nix").read_text()
    devenv_defaults = (REPO_ROOT / "devenv/default.nix").read_text()
    project = (REPO_ROOT / "pyproject.toml").read_text()
    project_map = (REPO_ROOT / "luxnix.yml").read_text()

    assert "jq" in packages.split()
    assert "black" not in packages.split()
    assert "python312" not in packages.split()
    assert '"black>=23.7.0"' in project
    assert "builtins.readFile ./.python-version" in devenv_config
    assert "pkgs.python312" not in devenv_config
    assert "package = python;" in devenv_config
    assert "devenvPackages = devenvUtils.packages;" in devenv_config
    assert "packages = import ./packages.nix" in devenv_defaults
    assert "development_packages: devenv/packages.nix" in project_map
    assert "containers = devenv_utils.containers" not in devenv_config
    assert not (REPO_ROOT / "devenv/build_inputs.nix").exists()
    assert not (REPO_ROOT / "devenv/runtime_packages.nix").exists()
    assert not (REPO_ROOT / "devenv/environment.nix").exists()


def test_devenv_owns_uv_sync_and_enter_shell_activates_the_managed_venv():
    devenv_config = (REPO_ROOT / "devenv.nix").read_text()

    assert "sync.enable = true;" in devenv_config
    assert "SYNC_STAMP" not in devenv_config
    assert "SYNC_CMD" not in devenv_config
    assert devenv_config.count("source .devenv/state/venv/bin/activate") == 1
    assert "source .env.systemd" in devenv_config
