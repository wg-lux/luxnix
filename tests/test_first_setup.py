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


def facts(**changes):
    return {
        "enabled": True,
        "center": False,
        "legacy": True,
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


def test_an_unchanged_choice_writes_nothing():
    current = facts(center=True, center_key=CENTER)
    assert first.settings_for(first.Choice(CENTER, True), {}, current) == []


def test_center_settings_are_quoted_for_nix_and_enable_vault_auth():
    settings = first.settings_for(
        first.Choice(CENTER, True), {"host_roles": {}}, facts(defer=True)
    )
    written = {s["key"]: s["value"] for s in settings}
    assert written[CENTER_KEY] == "true"
    assert written["endoreg_client.defaultCenterKey"] == f'"{CENTER}"'
    assert written["vault.client.auth.deferUntilProvisioned"] == "false"


def test_existing_center_key_spelling_is_kept():
    inventory = {"host_roles": {"endoreg-client.defaultCenterKey": "old"}}
    settings = first.settings_for(first.Choice(CENTER, True), inventory, facts())
    assert "endoreg-client.defaultCenterKey" in {s["key"] for s in settings}
    assert "endoreg_client.defaultCenterKey" not in {s["key"] for s in settings}


def test_machine_settings_leave_vault_auth_and_center_alone():
    current = facts(center=True, center_key=CENTER)
    settings = first.settings_for(first.Choice(None, True), {}, current)
    assert settings == [
        {"section": "host_services", "key": CENTER_KEY, "value": "false"}
    ]


def test_a_new_choice_is_always_the_hosts_own_salt(monkeypatch):
    assert first.ask_choice(None) == first.Choice(None, True)


def test_a_host_on_an_active_center_salt_cannot_change(monkeypatch):
    with pytest.raises(migration.MigrationError, match="no supported way"):
        first.ask_choice({"center_id": CENTER})


@pytest.mark.parametrize("reply", ["", "3", "maybe"])
def test_missing_center_salt_stops_unless_a_choice_is_made(monkeypatch, reply):
    monkeypatch.setattr(first, "center_salt_delivered", lambda center: False)
    answers(monkeypatch, reply)
    with pytest.raises(first.Stopped):
        first.require_delivery("gc-09", CENTER)


def test_confirmed_enrollment_records_no_acceptance(monkeypatch):
    monkeypatch.setattr(first, "center_salt_delivered", lambda center: False)
    answers(monkeypatch, "1")
    assert first.require_delivery("gc-09", CENTER) is None


def test_continuing_without_enrollment_names_who_accepted(monkeypatch, capsys):
    monkeypatch.setattr(first, "center_salt_delivered", lambda center: False)
    answers(monkeypatch, "2", "ACCEPT DATA LOSS gc-09", "A. Operator")
    assert first.require_delivery("gc-09", CENTER) == "A. Operator"
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
    monkeypatch.setattr(first, "center_salt_delivered", lambda center: True)
    answers(monkeypatch)
    first.require_delivery("gc-09", CENTER)


def console(monkeypatch, current, keyring=None):
    monkeypatch.setattr(first, "evaluate", lambda *a: current)
    monkeypatch.setattr(first, "established_keyring", lambda: keyring)
    monkeypatch.setattr(first, "vault_status", lambda *a: "ready")
    monkeypatch.setattr(first, "center_salt_delivered", lambda center: True)


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
    monkeypatch.setattr(first, "established_keyring", lambda: None)
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


def test_a_host_on_its_own_salt_is_not_offered_a_change(monkeypatch, tmp_path):
    console(monkeypatch, facts())
    monkeypatch.setattr(first, "write_inventory", lambda *a: pytest.fail("no write"))
    answers(monkeypatch, "2")
    with pytest.raises(first.Stopped):
        first.run(tmp_path, "gc-09")


def test_the_salt_unit_creates_only_in_machine_mode():
    unit = ROOT / (
        "modules/nixos/services/lx-annotate-local/subservices/"
        "lx-annotate-identity-salts.nix"
    )
    assert (
        'lib.optionalString (!cfg.django.centerIdentitySalt) "--allow-create"'
        in unit.read_text()
    )


def test_a_host_salt_needs_no_vault_or_enrollment(monkeypatch, tmp_path, capsys):
    console(monkeypatch, facts())
    monkeypatch.setattr(first, "vault_status", lambda *a: pytest.fail("no Vault"))
    monkeypatch.setattr(
        first, "center_salt_delivered", lambda center: pytest.fail("no center")
    )
    answers(monkeypatch, "1")
    assert first.run(tmp_path, "gc-09") is None
    output = capsys.readouterr().out
    assert "the hub never holds it" in output
    assert "creates one on first start" in output


def test_a_result_differing_from_the_choice_is_an_error(monkeypatch, tmp_path):
    inventory = tmp_path / "ansible/inventory/host_vars"
    inventory.mkdir(parents=True)
    (inventory / "gc-09.yml").write_text("host_roles: {}\n")
    monkeypatch.setattr(first, "evaluate", lambda *a: facts())
    monkeypatch.setattr(first, "write_inventory", lambda *a: None)
    monkeypatch.setattr(first, "regenerate", lambda checkout: None)
    with pytest.raises(migration.MigrationError, match="differs from your choice"):
        first.apply_choice(tmp_path, "gc-09", first.Choice(CENTER, True), facts())


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
            {"section": "host_services", "key": CENTER_KEY, "value": "true"},
            {
                "section": "host_roles",
                "key": "endoreg_client.defaultCenterKey",
                "value": f'"{CENTER}"',
            },
            {
                "section": "host_luxnix",
                "key": "vault.client.auth.deferUntilProvisioned",
                "value": "false",
            },
        ],
    )
    text = path.read_text()
    assert "# Würzburg shares one center salt." in text
    written = yaml.safe_load(text)
    assert written["host_services"][CENTER_KEY] == "true"
    assert written["host_roles"]["endoreg_client.defaultCenterKey"] == f'"{CENTER}"'
    assert written["host_roles"]["custom_packages.baseDevelopment"] == "true"
    assert written["host_luxnix"]["vault.client.auth.deferUntilProvisioned"] == "false"
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
    path = playbook_checkout(tmp_path, "host_services:\n  a: b\n")
    with pytest.raises(migration.MigrationError, match="playbook failed"):
        first.write_inventory(
            tmp_path,
            "gc-09",
            [
                {
                    "section": "host_luxnix",
                    "key": "vault.client.auth.deferUntilProvisioned",
                    "value": "false",
                }
            ],
        )
    assert "host_luxnix" not in path.read_text()


def test_salt_values_are_never_read():
    source = (ROOT / "lx_administration/storage/first_setup.py").read_text()
    assert source.count('privileged("cat"') == 1
    assert 'privileged("cat", str(KEYRING))' in source
