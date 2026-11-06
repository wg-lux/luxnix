"""First setup: inventory choices come first, and a salt can never move backwards."""

from pathlib import Path
import shutil

import pytest
import yaml

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import first_setup as first

CENTER = "university_hospital_wuerzburg"
ROOT = Path(__file__).resolve().parent.parent
CENTER_KEY = f"{first.DJANGO}.centerIdentitySalt"
LEGACY_KEY = f"{first.DJANGO}.enrollLegacyDefaultSalt"
CREATE_KEY = f"{first.DJANGO}.createInitialIdentitySalt"


def facts(**changes):
    return {
        "enabled": True,
        "center": False,
        "legacy": True,
        "create": False,
        "keyring": "/etc/secrets/vault/keyring.yml",
        "vault_dir": "/etc/secrets/vault",
        "center_key": None,
        "defer": False,
        "vault_address": "https://vault.example:8200",
        "vault_ca": None,
        "centers": [CENTER],
        "node_center": CENTER,
        "listed": True,
    } | changes


def answers(monkeypatch, *values):
    replies = iter(values)
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))


def test_an_active_center_salt_cannot_be_left_or_changed():
    active = {"center_id": CENTER}
    assert "no supported way" in first.refusal(first.Choice(None, True), active)
    other = first.Choice("rbk_stuttgart", True)
    assert "no supported way" in first.refusal(other, active)
    assert first.refusal(first.Choice(CENTER, True), active) is None


def test_the_legacy_reader_cannot_be_turned_off_once_established():
    keyring = {"allow_legacy_default_salt": True}
    assert "default salt" in first.refusal(first.Choice(None, False), keyring)


def test_a_locked_host_is_not_treated_as_established():
    assert first.refusal(first.Choice(None, False), None) is None


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"centers": []}, "not opted in"),
        ({"listed": False}, "not a provisioned node"),
        ({"node_center": "rbk_stuttgart"}, "grant no access"),
    ],
)
def test_center_needs_gs02_to_grant_this_site(changes, expected):
    assert expected in first.center_problem("gc-09", CENTER, facts(**changes))


def test_center_problem_passes_a_configured_site():
    assert first.center_problem("gc-09", CENTER, facts()) is None


def test_moving_to_a_host_salt_clears_the_center_setting_only():
    current = facts(center=True, center_key=CENTER)
    assert first.host_salt_settings(current, create=False) == [
        {"section": "host_services", "key": CENTER_KEY, "value": "false"}
    ]


def test_moving_to_a_host_salt_restores_the_unit_that_creates_it():
    settings = first.host_salt_settings(
        facts(center=True, legacy=False), create=False
    )
    assert {"section": "host_services", "key": LEGACY_KEY, "value": "true"} in settings


def test_a_host_on_an_active_center_salt_is_not_offered_a_move(
    monkeypatch, tmp_path, capsys
):
    current = facts(center=True, center_key=CENTER)
    console(monkeypatch, current, keyring={"center_id": CENTER})
    monkeypatch.setattr(first, "write_inventory", lambda *a: pytest.fail("no write"))
    answers(monkeypatch, "2")
    with pytest.raises(first.Stopped):
        first.run(tmp_path, "gc-09")
    assert "2. Use this host" not in capsys.readouterr().out


@pytest.mark.parametrize("reply", ["", "3", "maybe"])
def test_missing_center_salt_stops_unless_a_choice_is_made(monkeypatch, reply):
    monkeypatch.setattr(first, "center_salt_delivered", lambda center, vault_dir: False)
    answers(monkeypatch, reply)
    with pytest.raises(first.Stopped):
        first.require_delivery("gc-09", CENTER, "/vault")


def test_confirmed_enrollment_records_no_acceptance(monkeypatch):
    monkeypatch.setattr(first, "center_salt_delivered", lambda center, vault_dir: False)
    answers(monkeypatch, "1")
    assert first.require_delivery("gc-09", CENTER, "/vault") is None


def test_continuing_without_enrollment_names_who_accepted(monkeypatch, capsys):
    monkeypatch.setattr(first, "center_salt_delivered", lambda center, vault_dir: False)
    answers(monkeypatch, "2", "ACCEPT DATA LOSS gc-09", "A. Operator")
    assert first.require_delivery("gc-09", CENTER, "/vault") == "A. Operator"
    assert "stays stopped" in capsys.readouterr().out


@pytest.mark.parametrize(
    "replies",
    [("yes",), ("accept data loss gc-09",), ("ACCEPT DATA LOSS gc-10",),
     ("ACCEPT DATA LOSS gc-09", "")],
)  # fmt: skip
def test_data_loss_needs_the_exact_phrase_and_a_name(monkeypatch, replies):
    answers(monkeypatch, *replies)
    with pytest.raises(first.Stopped):
        first.accept_data_loss("gc-09", "consequence")


def test_delivered_center_salt_asks_nothing(monkeypatch):
    monkeypatch.setattr(first, "center_salt_delivered", lambda center, vault_dir: True)
    answers(monkeypatch)
    first.require_delivery("gc-09", CENTER, "/vault")


def console(monkeypatch, current, keyring=None, status=None):
    known = status or (first.ESTABLISHED if keyring else first.NO_SALT)
    monkeypatch.setattr(first, "evaluate", lambda *a: current)
    monkeypatch.setattr(first, "read_keyring", lambda facts: (known, keyring))
    monkeypatch.setattr(first, "vault_status", lambda *a: "ready")
    monkeypatch.setattr(first, "center_salt_delivered", lambda center, vault_dir: True)


def test_keeping_settings_writes_nothing_and_succeeds(monkeypatch, tmp_path, capsys):
    console(monkeypatch, facts(center=True, center_key=CENTER))
    monkeypatch.setattr(
        first, "write_inventory", lambda *a: pytest.fail("must not write")
    )
    answers(monkeypatch, "1")
    first.run(tmp_path, "gc-09")
    assert "SUCCESS: First setup is settled" in capsys.readouterr().err


def test_stop_changes_nothing(monkeypatch, tmp_path):
    console(monkeypatch, facts())
    answers(monkeypatch, "3")
    with pytest.raises(first.Stopped):
        first.run(tmp_path, "gc-09")


def test_a_conflicting_inventory_is_reported_before_any_question(monkeypatch, tmp_path):
    console(monkeypatch, facts(), keyring={"center_id": CENTER})
    answers(monkeypatch)
    with pytest.raises(migration.MigrationError, match="Inventory conflicts"):
        first.run(tmp_path, "gc-09")


def test_a_host_without_lx_annotate_is_not_asked(monkeypatch, tmp_path, capsys):
    console(monkeypatch, facts(enabled=False))
    answers(monkeypatch)
    first.run(tmp_path, "gc-09")
    assert "needs no salt choice" in capsys.readouterr().out


def test_moving_to_a_host_salt_writes_regenerates_and_asks_for_a_commit(
    monkeypatch, tmp_path, capsys
):
    inventory = tmp_path / "ansible/inventory/host_vars"
    inventory.mkdir(parents=True)
    (inventory / "gc-09.yml").write_text("host_services: {}\n")
    states = iter([facts(center=True, center_key=CENTER), facts()])
    monkeypatch.setattr(first, "evaluate", lambda *a: next(states))
    monkeypatch.setattr(first, "read_keyring", lambda f: (first.ESTABLISHED, {}))
    monkeypatch.setattr(first, "vault_status", lambda *a: "ready")
    written = []
    monkeypatch.setattr(first, "write_inventory", lambda *a: written.append(a[2]))
    monkeypatch.setattr(first, "regenerate", lambda checkout: written.append("gen"))
    answers(monkeypatch, "2")
    with pytest.raises(first.Stopped, match="after this commit"):
        first.run(tmp_path, "gc-09")
    assert written[0] == [
        {"section": "host_services", "key": CENTER_KEY, "value": "false"}
    ]
    assert written[1] == "gen"
    output = capsys.readouterr().out
    assert "recommended" in output
    assert "git commit" in output


def test_a_host_with_its_own_salt_is_not_offered_a_change(monkeypatch, tmp_path):
    console(monkeypatch, facts(), keyring={"schema_version": 1})
    monkeypatch.setattr(first, "write_inventory", lambda *a: pytest.fail("no write"))
    answers(monkeypatch, "2")
    with pytest.raises(first.Stopped):
        first.run(tmp_path, "gc-09")


def test_a_host_with_no_salt_is_offered_creating_one(monkeypatch, tmp_path, capsys):
    inventory = tmp_path / "ansible/inventory/host_vars"
    inventory.mkdir(parents=True)
    (inventory / "gc-09.yml").write_text("host_services: {}\n")
    console(monkeypatch, facts())
    written = []
    monkeypatch.setattr(first, "write_inventory", lambda *a: written.append(a[2]))
    monkeypatch.setattr(first, "regenerate", lambda checkout: None)
    answers(monkeypatch, "2")
    with pytest.raises(first.Stopped, match="after this commit"):
        first.run(tmp_path, "gc-09")
    assert written == [
        [{"section": "host_services", "key": CREATE_KEY, "value": "true"}]
    ]
    assert "create a random salt" in capsys.readouterr().out


def test_no_salt_can_still_continue_for_a_custody_restore(
    monkeypatch, tmp_path, capsys
):
    console(monkeypatch, facts())
    monkeypatch.setattr(first, "write_inventory", lambda *a: pytest.fail("no write"))
    answers(monkeypatch, "1")
    assert first.run(tmp_path, "gc-09") is None
    assert "SUCCESS" in capsys.readouterr().err


def test_unknown_storage_locks_only_the_irreversible_move(
    monkeypatch, tmp_path, capsys
):
    console(monkeypatch, facts(center=True, center_key=CENTER), status=first.UNKNOWN)
    monkeypatch.setattr(first, "write_inventory", lambda *a: pytest.fail("no write"))
    answers(monkeypatch, "1")
    first.run(tmp_path, "gc-09")
    captured = capsys.readouterr()
    assert "until storage is unlocked" in captured.out
    assert "2. Use this host" not in captured.out
    assert "SUCCESS" in captured.err


def privileged_results(monkeypatch, results):
    class Result:
        def __init__(self, returncode, stdout=b""):
            self.returncode, self.stdout = returncode, stdout

    monkeypatch.setattr(
        first.secret_preflight,
        "privileged",
        lambda *command: Result(*results[command[0]]),
    )


def test_keyring_states_are_told_apart(monkeypatch):
    privileged_results(monkeypatch, {"cat": (0, b"center_id: x\n")})
    assert first.read_keyring(facts()) == (first.ESTABLISHED, {"center_id": "x"})
    privileged_results(monkeypatch, {"cat": (1,), "find": (0, b"/vault/other\n")})
    assert first.read_keyring(facts()) == (first.NO_SALT, None)
    privileged_results(monkeypatch, {"cat": (1,), "find": (0, b"")})
    assert first.read_keyring(facts()) == (first.UNKNOWN, None)
    privileged_results(monkeypatch, {"cat": (1,), "find": (1,)})
    assert first.read_keyring(facts()) == (first.UNKNOWN, None)
    privileged_results(monkeypatch, {"cat": (0, b"a: [")})
    assert first.read_keyring(facts()) == (first.UNKNOWN, None)


def test_salt_creation_is_a_per_host_setting():
    unit = ROOT / (
        "modules/nixos/services/lx-annotate-local/subservices/"
        "lx-annotate-identity-salts.nix"
    )
    assert (
        'lib.optionalString cfg.django.createInitialIdentitySalt "--allow-create"'
        in unit.read_text()
    )


def test_a_host_salt_needs_no_vault_or_enrollment(monkeypatch, tmp_path, capsys):
    console(monkeypatch, facts())
    monkeypatch.setattr(first, "vault_status", lambda *a: pytest.fail("no Vault"))
    monkeypatch.setattr(
        first, "center_salt_delivered", lambda *a: pytest.fail("no center")
    )
    answers(monkeypatch, "1")
    assert first.run(tmp_path, "gc-09") is None
    output = capsys.readouterr().out
    assert "the hub never holds it" in output
    assert "none found" in output


def test_a_result_differing_from_the_choice_is_an_error(monkeypatch, tmp_path):
    inventory = tmp_path / "ansible/inventory/host_vars"
    inventory.mkdir(parents=True)
    (inventory / "gc-09.yml").write_text("host_services: {}\n")
    current = facts(center=True, center_key=CENTER)
    monkeypatch.setattr(first, "evaluate", lambda *a: current)
    monkeypatch.setattr(first, "write_inventory", lambda *a: None)
    monkeypatch.setattr(first, "regenerate", lambda checkout: None)
    with pytest.raises(migration.MigrationError, match="differs from your choice"):
        first.move_to_host_salt(tmp_path, "gc-09", current, create=False)


def test_a_malformed_inventory_stops_before_any_write(monkeypatch, tmp_path):
    inventory = tmp_path / "ansible/inventory/host_vars"
    inventory.mkdir(parents=True)
    (inventory / "gc-09.yml").write_text("a: 1\na: 2\n")
    monkeypatch.setattr(first, "write_inventory", lambda *a: pytest.fail("no write"))
    with pytest.raises(yaml.YAMLError):
        first.move_to_host_salt(tmp_path, "gc-09", facts(), create=False)


def playbook_checkout(tmp_path, inventory):
    (tmp_path / "ansible/playbooks").mkdir(parents=True)
    (tmp_path / "ansible/inventory/host_vars").mkdir(parents=True)
    shutil.copy(ROOT / first.PLAYBOOK, tmp_path / first.PLAYBOOK)
    path = tmp_path / "ansible/inventory/host_vars/gc-09.yml"
    path.write_text(inventory)
    return path


INVENTORY = """\
# inventory/host_vars/gc-09.yml
---
host_roles:
  custom_packages.baseDevelopment: "true"

host_services:
  # Würzburg shares one center salt.
  luxnix.lxAnnotateLocal.django.centerIdentitySalt: "false"

host_luxnix:
  other.setting: "true"
"""
needs_ansible = pytest.mark.skipif(
    shutil.which("ansible-playbook") is None, reason="ansible-playbook is missing"
)


@needs_ansible
def test_real_playbook_writes_choices_and_keeps_everything_else(tmp_path):
    path = playbook_checkout(tmp_path, INVENTORY)
    first.write_inventory(
        tmp_path,
        "gc-09",
        [
            {"section": "host_services", "key": CENTER_KEY, "value": "false"},
            {"section": "host_services", "key": LEGACY_KEY, "value": "true"},
        ],
    )
    text = path.read_text()
    assert "# Würzburg shares one center salt." in text
    written = yaml.safe_load(text)
    assert written["host_services"][CENTER_KEY] == "false"
    assert written["host_services"][LEGACY_KEY] == "true"
    assert written["host_roles"]["custom_packages.baseDevelopment"] == "true"
    assert written["host_luxnix"]["other.setting"] == "true"
    assert text.count(CENTER_KEY) == 1


@needs_ansible
def test_real_playbook_refuses_a_setting_it_does_not_own(tmp_path, capsys):
    path = playbook_checkout(tmp_path, INVENTORY)
    before = path.read_text()
    with pytest.raises(migration.MigrationError, match="playbook failed"):
        first.write_inventory(
            tmp_path,
            "gc-09",
            [{"section": "host_luxnix", "key": "security.sudo.enable", "value": "x"}],
        )
    assert path.read_text() == before


@needs_ansible
def test_real_playbook_refuses_an_inventory_without_the_section(tmp_path):
    path = playbook_checkout(tmp_path, "host_roles:\n  a: b\n")
    with pytest.raises(migration.MigrationError, match="playbook failed"):
        first.write_inventory(
            tmp_path,
            "gc-09",
            [{"section": "host_services", "key": CENTER_KEY, "value": "false"}],
        )
    assert CENTER_KEY not in path.read_text()


@needs_ansible
def test_real_playbook_no_longer_writes_center_or_vault_settings(tmp_path):
    path = playbook_checkout(tmp_path, INVENTORY)
    before = path.read_text()
    for section, key in (
        ("host_roles", "endoreg_client.defaultCenterKey"),
        ("host_luxnix", "vault.client.auth.deferUntilProvisioned"),
    ):
        with pytest.raises(migration.MigrationError, match="playbook failed"):
            first.write_inventory(
                tmp_path, "gc-09", [{"section": section, "key": key, "value": "x"}]
            )
    assert path.read_text() == before


def test_salt_values_are_never_read():
    source = (ROOT / "lx_administration/storage/first_setup.py").read_text()
    assert source.count('privileged("cat"') == 1
    assert 'privileged("cat", facts["keyring"])' in source
