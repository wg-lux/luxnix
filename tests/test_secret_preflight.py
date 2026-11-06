"""Preflight requires only needed secrets and refuses anything it cannot prove."""

import json
import os
from pathlib import Path
import shutil
import time
import warnings

import pytest

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import boot_setup as setup
from lx_administration.storage import recovery_custody
from lx_administration.storage import secret_preflight as preflight

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import crypt

PASSWORD = "synthetic-test-passphrase"
ADMIN_HASH = crypt.crypt(PASSWORD, "$6$syntheticsalt$") + "\n"
CLIENT_HASH = crypt.crypt("another-synthetic-value", "$6$syntheticsalt$") + "\n"


@pytest.fixture
def environment(tmp_path, monkeypatch):
    """Synthetic host files and custody; real cmp, diff and crypt, no real secrets."""
    live = tmp_path / "live"
    live.mkdir()
    (live / "admin.hash").write_text(ADMIN_HASH)
    (live / "client.hash").write_text(CLIENT_HASH)
    (live / "master").write_text("synthetic-master-key")
    (live / "salts").mkdir()
    (live / "salts" / "salt").write_text("synthetic-salt")
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700)
    items = [
        {
            "kind": "account",
            "id": "admin-password-hash",
            "path": str(live / "admin.hash"),
        },
        {
            "kind": "account",
            "id": "client-password-hash",
            "path": str(live / "client.hash"),
        },
        {"kind": "data", "id": "lx-annotate-master-key", "path": str(live / "master")},
        {"kind": "data", "id": "identity-salt-recovery", "path": str(live / "salts")},
    ]
    state = tmp_path / "state"
    state.mkdir()
    (state / ".lock").touch(mode=0o600)
    payload = {
        "schema_version": 1,
        "spec": {
            "schema_version": 1,
            "host": "gc-09",
            "checkout": "/home/admin/release",
            "hardware_uuid": "12345678-1234-1234-1234-123456789abc",
            "source_retention": "discard-approved",
            "installation": "disposable",
            "disks": [
                {"path": "/dev/disk/by-id/test", "serial": "s", "size_bytes": 1000}
            ],
        },
        "source": {"revision": "abc", "lock_sha256": "def"},
        "config": {
            "closure": "/nix/store/" + "a" * 32 + "-nixos-system-gc-09",
            "secure_boot": False,
            "crypttab": "",
            "admin": {"name": "synthetic-admin-without-home"},
            "secret_contract": {
                "vault_server": False,
                "openbao": False,
                "items": items,
            },
        },
    }
    plan = payload | {"plan_id": migration.digest(payload)}
    migration.atomic_json(state / "plan.json", plan)
    migration.atomic_json(
        state / "progress.json",
        {
            "plan_id": plan["plan_id"],
            "attestations": {},
            "install": {"status": "pending"},
        },
    )
    monkeypatch.setattr(migration, "private_path", lambda *a, **k: None)
    monkeypatch.setattr(migration, "verify_source", lambda *a: None)
    monkeypatch.setattr(migration, "validate_spec", lambda *a: None)
    monkeypatch.setattr(preflight, "root_prefix", list)
    monkeypatch.setattr(preflight, "require_target_host", lambda *a: None)
    monkeypatch.setattr(preflight, "retained_volume_keys", lambda *a: [])
    monkeypatch.setattr(preflight, "encrypted_storage", lambda *a, **k: None)
    monkeypatch.setattr(recovery_custody, "storage_disks", lambda *a: {"/dev/other"})
    monkeypatch.setattr(preflight.getpass, "getpass", lambda *a: PASSWORD)
    monkeypatch.setattr(preflight.sys.stdin, "isatty", lambda: True, raising=False)
    return state, plan, custody, live


def fill_custody(custody, live, host="gc-09"):
    for path in live.rglob("*"):
        target = custody / host / "secrets" / str(path).lstrip("/")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())


def copy_of(custody, path):
    return custody / "gc-09" / "secrets" / str(path).lstrip("/")


def statuses(receipt):
    return {item["id"]: item["status"] for item in receipt["items"]}


def test_complete_custody_writes_a_receipt_without_values(environment):
    state, plan, custody, live = environment
    fill_custody(custody, live)
    receipt = preflight.run(state, custody)
    assert set(statuses(receipt).values()) == {"verified"}
    assert receipt["plan_id"] == plan["plan_id"]
    assert receipt["admin_password_verified"] is True
    written = (state / migration.PREFLIGHT_RECEIPT).read_text()
    for value in (ADMIN_HASH.strip(), PASSWORD, "synthetic-master-key"):
        assert value not in written
    migration.require_preflight(state)


def test_only_items_in_the_evaluated_contract_are_required(environment):
    state, plan, custody, live = environment
    fill_custody(custody, live)
    (live / "regenerated-django-key").write_text("not in the contract")
    assert "regenerated" not in str(statuses(preflight.run(state, custody)))


def test_missing_copy_reports_a_hint_and_writes_no_receipt(environment, capsys):
    state, _, custody, live = environment
    fill_custody(custody, live)
    copy_of(custody, live / "master").unlink()
    with pytest.raises(preflight.PreflightError, match="not-in-custody"):
        preflight.run(state, custody)
    assert "sudo install -D -m 0600" in capsys.readouterr().out
    assert not (state / migration.PREFLIGHT_RECEIPT).exists()


def test_stale_copy_is_refused(environment):
    state, _, custody, live = environment
    fill_custody(custody, live)
    (live / "master").write_text("rotated after the copy was made")
    with pytest.raises(preflight.PreflightError, match="differs"):
        preflight.run(state, custody)


def test_changed_file_in_directory_copy_is_refused(environment):
    state, _, custody, live = environment
    fill_custody(custody, live)
    (live / "salts" / "added").write_text("new salt")
    with pytest.raises(preflight.PreflightError, match="differs"):
        preflight.run(state, custody)


def test_absent_item_stops_because_a_locked_container_looks_the_same(environment):
    state, _, custody, live = environment
    fill_custody(custody, live)
    (live / "master").unlink()
    with pytest.raises(preflight.PreflightError, match="absent-on-host"):
        preflight.run(state, custody)


def test_stated_absence_is_recorded(environment):
    state, _, custody, live = environment
    fill_custody(custody, live)
    (live / "master").unlink()
    copy_of(custody, live / "master").unlink()
    receipt = preflight.run(
        state, custody, accept_absent=("lx-annotate-master-key",)
    )
    assert statuses(receipt)["lx-annotate-master-key"] == "accepted-absent"
    migration.require_preflight(state)


def test_absent_account_hash_still_needs_a_valid_custody_copy(environment):
    state, _, custody, live = environment
    fill_custody(custody, live)
    (live / "client.hash").unlink()
    copy_of(custody, live / "client.hash").unlink()
    with pytest.raises(preflight.PreflightError, match="not-in-custody"):
        preflight.run(state, custody, accept_absent=("client-password-hash",))


def test_unrequired_acceptance_is_refused(environment):
    state, _, custody, live = environment
    fill_custody(custody, live)
    with pytest.raises(preflight.PreflightError, match="Not required"):
        preflight.run(state, custody, accept_absent=("made-up-item",))


def test_malformed_account_hash_is_refused(environment):
    state, _, custody, live = environment
    (live / "client.hash").write_text("!locked\n")
    fill_custody(custody, live)
    with pytest.raises(preflight.PreflightError, match="invalid-hash"):
        preflight.run(state, custody)


def test_wrong_admin_password_is_a_lockout_and_writes_no_receipt(
    environment, monkeypatch
):
    state, _, custody, live = environment
    fill_custody(custody, live)
    monkeypatch.setattr(preflight.getpass, "getpass", lambda *a: "not the password")
    with pytest.raises(preflight.PreflightError, match="lock you out"):
        preflight.run(state, custody)
    assert not (state / migration.PREFLIGHT_RECEIPT).exists()


def test_failed_rerun_removes_the_earlier_receipt(environment):
    state, _, custody, live = environment
    fill_custody(custody, live)
    preflight.run(state, custody)
    assert (state / migration.PREFLIGHT_RECEIPT).exists()
    (live / "master").write_text("changed")
    with pytest.raises(preflight.PreflightError):
        preflight.run(state, custody)
    assert not (state / migration.PREFLIGHT_RECEIPT).exists()


def test_custody_on_an_erased_disk_is_refused(environment, monkeypatch):
    state, plan, custody, live = environment
    fill_custody(custody, live)
    selected = os.path.realpath(plan["spec"]["disks"][0]["path"])
    monkeypatch.setattr(recovery_custody, "storage_disks", lambda *a: {selected})
    with pytest.raises(preflight.PreflightError, match="disk this plan selects"):
        preflight.run(state, custody)


def test_missing_custody_directory_is_explained(environment, tmp_path):
    state, _, _, _ = environment
    with pytest.raises(preflight.PreflightError, match="Mount your encrypted custody"):
        preflight.run(state, tmp_path.resolve() / "not-mounted")


def test_unencrypted_custody_is_refused(environment, monkeypatch):
    state, _, custody, live = environment
    fill_custody(custody, live)

    def plain(*a, **k):
        raise ValueError("Secret storage must be backed by an encrypted device")

    monkeypatch.setattr(preflight, "encrypted_storage", plain)
    with pytest.raises(ValueError, match="encrypted device"):
        preflight.run(state, custody)


def test_shared_custody_directory_is_refused(environment):
    state, _, custody, live = environment
    fill_custody(custody, live)
    custody.chmod(0o755)
    with pytest.raises(preflight.PreflightError, match="private directory"):
        preflight.run(state, custody)


@pytest.mark.parametrize("server", ["vault_server", "openbao"])
def test_secrets_server_host_fails_closed(environment, server):
    state, plan, custody, _ = environment
    payload = {k: v for k, v in plan.items() if k != "plan_id"}
    payload["config"]["secret_contract"][server] = True
    migration.atomic_json(
        state / "plan.json", payload | {"plan_id": migration.digest(payload)}
    )
    with pytest.raises(preflight.PreflightError, match="vault-server-rebuild"):
        preflight.run(state, custody)


def test_plan_without_a_contract_requires_a_new_plan(environment):
    state, plan, custody, _ = environment
    payload = {k: v for k, v in plan.items() if k != "plan_id"}
    del payload["config"]["secret_contract"]
    migration.atomic_json(
        state / "plan.json", payload | {"plan_id": migration.digest(payload)}
    )
    with pytest.raises(migration.MigrationError, match="create a new plan"):
        preflight.run(state, custody)


def controller(environment, tmp_path, monkeypatch):
    """A synthetic admin vault on this host, with its key on separate custody."""
    from ansible.parsing.vault import VaultLib, VaultSecret

    state, plan, custody, live = environment
    fill_custody(custody, live)
    key_text = b"synthetic-vault-key-material"
    home = tmp_path / "home" / "operator"
    (home / ".lxv" / "secrets").mkdir(parents=True)
    (home / ".lxv" / "deploy").mkdir()
    (home / ".lxv.key").write_bytes(key_text)
    secret = VaultSecret(key_text)
    record = VaultLib([("luxnix-master", secret)]).encrypt(
        b"synthetic-record", secret=secret, vault_id="luxnix-master"
    )
    (home / ".lxv" / "secrets" / "record").write_bytes(record)
    (home / ".lxv" / "deploy" / "derived").write_bytes(b"not preserved")
    copy = custody / "controller" / ".lxv" / "secrets"
    copy.mkdir(parents=True)
    (copy / "record").write_bytes(record)
    key_custody = tmp_path / "key-media" / "lxv.key"
    key_custody.parent.mkdir(mode=0o700)
    key_custody.write_bytes(key_text)
    key_custody.chmod(0o600)
    actual_path = Path

    class HomePath(type(Path())):
        def __truediv__(self, other):
            if str(self) == "/home":
                return actual_path(home.parent) / "operator"
            return super().__truediv__(other)

    monkeypatch.setattr(preflight, "Path", HomePath)
    monkeypatch.setattr(recovery_custody, "private", lambda *a, **k: None)
    monkeypatch.setattr(recovery_custody, "independent", lambda *a: None)
    return state, custody, key_custody, home


def test_controller_needs_its_key_on_separate_media(
    environment, tmp_path, monkeypatch
):
    state, custody, _, _ = controller(environment, tmp_path, monkeypatch)
    with pytest.raises(preflight.PreflightError, match="vault-key-custody"):
        preflight.run(state, custody)


def test_controller_copy_is_decrypted_with_the_key_copy(
    environment, tmp_path, monkeypatch
):
    state, custody, key_custody, _ = controller(environment, tmp_path, monkeypatch)
    receipt = preflight.run(state, custody, key_custody=key_custody)
    assert receipt["controller"] == {"present": True, "records_decrypted": 1}


def test_key_copy_sharing_media_with_the_vault_copy_is_refused(
    environment, tmp_path, monkeypatch
):
    state, custody, key_custody, _ = controller(environment, tmp_path, monkeypatch)

    def shared(*a):
        raise recovery_custody.CustodyError("shares a physical disk")

    monkeypatch.setattr(recovery_custody, "independent", shared)
    with pytest.raises(preflight.PreflightError, match="shares a physical disk"):
        preflight.run(state, custody, key_custody=key_custody)


def test_corrupt_vault_record_copy_is_refused(environment, tmp_path, monkeypatch):
    state, custody, key_custody, home = controller(environment, tmp_path, monkeypatch)
    for root in (home / ".lxv", custody / "controller" / ".lxv"):
        (root / "secrets" / "record").write_bytes(
            b"$ANSIBLE_VAULT;1.2;AES256;luxnix-master\n3132333435\n"
        )
    with pytest.raises(preflight.PreflightError, match="cannot decrypt"):
        preflight.run(state, custody, key_custody=key_custody)


def test_wrong_key_copy_is_refused(environment, tmp_path, monkeypatch):
    state, custody, key_custody, _ = controller(environment, tmp_path, monkeypatch)
    key_custody.write_bytes(b"a different key entirely")
    with pytest.raises(preflight.PreflightError, match="key copy differs"):
        preflight.run(state, custody, key_custody=key_custody)


def test_volume_on_a_selected_disk_needs_no_old_key(environment, monkeypatch):
    _, plan, _, _ = environment
    # Restore the real selection; only the disk probes are synthetic.
    monkeypatch.undo()
    monkeypatch.setattr(
        migration.os,
        "stat",
        lambda path, **k: type("S", (), {"st_rdev": 1})(),
    )
    monkeypatch.setattr(migration.os.path, "exists", lambda p: True)
    disks = {"/dev/erased": {1}, "/dev/retained": {2}}
    monkeypatch.setattr(migration, "device_disks", lambda device: disks[device])
    plan = plan | {
        "config": plan["config"]
        | {
            "crypttab": "# comment\n"
            "one /dev/erased /etc/luks-keys/one.key luks\n"
            "two /dev/retained /etc/luks-keys/two.key luks\n"
            "three /dev/retained none luks\n"
        }
    }
    assert preflight.retained_volume_keys(plan) == [
        {"kind": "key", "id": "luks-key-two", "path": "/etc/luks-keys/two.key"}
    ]


@pytest.fixture
def receipt(environment):
    state, plan, custody, live = environment
    fill_custody(custody, live)
    preflight.run(state, custody)
    return state, plan, state / migration.PREFLIGHT_RECEIPT


@pytest.mark.parametrize(
    "change",
    [
        {"plan_id": "another-plan"},
        {"host": "gc-10"},
        {"admin_password_verified": False},
        {"recorded_at": time.time() - migration.MAX_AGE - 60},
        {"recorded_at": time.time() + 3600},
        {"items": []},
        {
            "items": [
                {"id": "admin-password-hash", "path": "/x", "status": "differs"},
            ]
        },
        {"unexpected": True},
    ],
)
def test_receipt_gate_rejects_anything_short_of_proof(receipt, change):
    state, plan, path = receipt
    path.write_text(json.dumps(json.loads(path.read_text()) | change))
    with pytest.raises(migration.MigrationError):
        migration.verify_preflight_receipt(path, plan)


def test_missing_receipt_names_the_command(environment):
    state, _, _, _ = environment
    with pytest.raises(migration.MigrationError, match="boot-storage-setup preflight"):
        migration.require_preflight(state)


def test_review_stops_before_any_prompt_without_a_receipt(
    environment, tmp_path, monkeypatch
):
    state, plan, _, _ = environment
    plan["spec"].update(installation="in-place", source_retention="in-place")
    plan["plan_id"] = migration.digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    )
    migration.atomic_json(state / "plan.json", plan)
    progress = json.loads((state / "progress.json").read_text())
    progress["plan_id"] = plan["plan_id"]
    migration.atomic_json(state / "progress.json", progress)
    monkeypatch.setattr(migration, "verify_readiness", lambda *a, **k: None)
    prompts = []
    monkeypatch.setattr("builtins.input", lambda *a: prompts.append(a) or "VERIFIED")
    report = tmp_path / "notes.txt"
    report.write_text("Synthetic results")
    with pytest.raises(migration.MigrationError, match="preflight"):
        setup.review(state, "Test reviewer", report)
    assert not prompts


def recovery_evidence(tmp_path, plan):
    artifact = tmp_path / "recovery-notes.txt"
    artifact.write_text("Synthetic results")
    report = tmp_path / "recovery-evidence.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plan_id": plan["plan_id"],
                "stage": "recovery",
                "checks": dict.fromkeys(
                    migration.required_checks("recovery", plan), True
                ),
                "artifacts": [str(artifact)],
            }
        )
    )
    return report


def test_attest_cannot_bypass_the_missing_receipt(environment, tmp_path):
    state, plan, _, _ = environment
    with pytest.raises(migration.MigrationError, match="preflight"):
        migration.attest(
            state, "recovery", recovery_evidence(tmp_path, plan), "Test reviewer"
        )
    assert migration.load_progress(state, plan)["attestations"] == {}


def test_attestation_binds_the_receipt_so_later_edits_invalidate_it(
    receipt, tmp_path
):
    state, plan, path = receipt
    migration.attest(
        state, "recovery", recovery_evidence(tmp_path, plan), "Test reviewer"
    )
    progress = migration.load_progress(state, plan)
    migration.check_attestation("recovery", plan, progress)
    assert any(
        Path(a["path"]).name == migration.PREFLIGHT_RECEIPT
        for a in progress["attestations"]["recovery"]["artifacts"]
    )
    path.write_text(path.read_text() + " ")
    with pytest.raises(migration.MigrationError, match="evidence changed"):
        migration.check_attestation("recovery", plan, progress)


def test_assessment_without_a_receipt_artifact_is_rejected(receipt, tmp_path):
    state, plan, _ = receipt
    migration.attest(
        state, "recovery", recovery_evidence(tmp_path, plan), "Test reviewer"
    )
    progress = migration.load_progress(state, plan)
    record = progress["attestations"]["recovery"]
    record["artifacts"] = [
        a for a in record["artifacts"]
        if Path(a["path"]).name != migration.PREFLIGHT_RECEIPT
    ]
    with pytest.raises(migration.MigrationError, match="no secret preflight receipt"):
        migration.check_attestation("recovery", plan, progress)


def as_migration(state, plan):
    payload = {k: v for k, v in plan.items() if k != "plan_id"}
    payload["spec"] = payload["spec"] | {
        "installation": "migration",
        "source_retention": "whole-disk-image",
    }
    migration.atomic_json(
        state / "plan.json", payload | {"plan_id": migration.digest(payload)}
    )


def with_identity_directory(state, plan, directory, extra=()):
    payload = {k: v for k, v in plan.items() if k != "plan_id"}
    contract = payload["config"]["secret_contract"]
    contract["identity_directory"] = str(directory)
    contract["items"] = [*contract["items"], *extra]
    migration.atomic_json(
        state / "plan.json", payload | {"plan_id": migration.digest(payload)}
    )


def test_data_key_cannot_be_waived_when_the_plan_keeps_data(environment):
    state, plan, custody, live = environment
    as_migration(state, plan)
    fill_custody(custody, live)
    (live / "master").unlink()
    copy_of(custody, live / "master").unlink()
    with pytest.raises(preflight.PreflightError, match="data-key-absent"):
        preflight.run(state, custody, accept_absent=("lx-annotate-master-key",))
    assert not (state / migration.PREFLIGHT_RECEIPT).exists()


def test_absent_data_key_explains_it_cannot_be_waived(environment, capsys):
    state, plan, custody, live = environment
    as_migration(state, plan)
    fill_custody(custody, live)
    (live / "master").unlink()
    with pytest.raises(preflight.PreflightError, match="absent-on-host"):
        preflight.run(state, custody)
    assert "cannot be waived" in capsys.readouterr().out


def test_non_migration_plan_warns_that_data_is_not_kept(environment, capsys):
    state, _, custody, live = environment
    fill_custody(custody, live)
    preflight.run(state, custody)
    assert "does not keep data" in capsys.readouterr().out


def test_salt_generations_found_on_the_host_are_required(environment):
    state, plan, custody, live = environment
    vault = live / "vault"
    vault.mkdir()
    (vault / "lx_annotate_identity_center_example").write_text("center salt")
    (vault / "lx_annotate_center_example_identity").write_text("center source")
    (vault / "unrelated_file").write_text("not a salt")
    with_identity_directory(state, plan, vault)
    fill_custody(custody, live)
    copy_of(custody, vault / "lx_annotate_identity_center_example").unlink()
    with pytest.raises(
        preflight.PreflightError,
        match="identity-file-lx_annotate_identity_center_example: not-in-custody",
    ):
        preflight.run(state, custody)
    fill_custody(custody, live)
    found = statuses(preflight.run(state, custody))
    assert found["identity-file-lx_annotate_identity_center_example"] == "verified"
    assert found["identity-file-lx_annotate_center_example_identity"] == "verified"
    assert not [name for name in found if "unrelated" in name]


def test_salt_referenced_by_the_keyring_is_required_even_if_stored_elsewhere(
    environment,
):
    state, plan, custody, live = environment
    vault = live / "vault"
    vault.mkdir()
    elsewhere = live / "retired-salt"
    elsewhere.write_text("retiring generation")
    keyring = vault / "lx_annotate_identity_keyring.yml"
    keyring.write_text(
        f"schema_version: 1\nactive: {elsewhere}\nretiring: [{elsewhere}]\n"
    )
    with_identity_directory(
        state,
        plan,
        vault,
        [{"kind": "data", "id": "identity-salt-keyring", "path": str(keyring)}],
    )
    fill_custody(custody, live)
    assert statuses(preflight.run(state, custody))["identity-file-retired-salt"]
    copy_of(custody, elsewhere).unlink()
    with pytest.raises(preflight.PreflightError, match="identity-file-retired-salt"):
        preflight.run(state, custody)


def remove_salts(live):
    shutil.rmtree(live / "salts")


def test_accepted_salt_loss_passes_and_names_who_accepted(environment):
    state, plan, custody, live = environment
    remove_salts(live)
    fill_custody(custody, live)
    receipt = preflight.run(state, custody, salt_loss_accepted_by="A. Operator")
    found = statuses(receipt)
    assert found["identity-salt-recovery"] == "accepted-loss"
    assert found["lx-annotate-master-key"] == "verified"
    assert receipt["salt_loss_accepted_by"] == "A. Operator"
    migration.verify_preflight_receipt(state / migration.PREFLIGHT_RECEIPT, plan)


def test_missing_salts_are_refused_without_acceptance(environment):
    state, _, custody, live = environment
    remove_salts(live)
    fill_custody(custody, live)
    with pytest.raises(preflight.PreflightError, match="identity-salt-recovery"):
        preflight.run(state, custody)


def test_accepting_loss_never_excuses_a_salt_still_on_this_host(environment):
    state, _, custody, live = environment
    with pytest.raises(preflight.PreflightError, match="identity-salt-recovery"):
        preflight.run(state, custody, salt_loss_accepted_by="A. Operator")


def test_accepting_loss_never_excuses_the_master_key(environment):
    # A locked container hides salts and this key together, so this still stops.
    state, _, custody, live = environment
    fill_custody(custody, live)
    remove_salts(live)
    copy_of(custody, live / "master").unlink()
    (live / "master").unlink()
    with pytest.raises(preflight.PreflightError, match="lx-annotate-master-key"):
        preflight.run(state, custody, salt_loss_accepted_by="A. Operator")


def test_missing_salts_lists_only_salts_absent_everywhere(environment):
    state, _, custody, live = environment
    assert preflight.missing_salts(state, custody) == []
    remove_salts(live)
    assert preflight.missing_salts(state, custody) == [str(live / "salts")]


def test_receipt_with_unnamed_loss_is_rejected(environment):
    state, plan, custody, live = environment
    remove_salts(live)
    fill_custody(custody, live)
    receipt = preflight.run(state, custody, salt_loss_accepted_by="A. Operator")
    del receipt["salt_loss_accepted_by"]
    (state / migration.PREFLIGHT_RECEIPT).write_text(json.dumps(receipt))
    with pytest.raises(migration.MigrationError, match="named person"):
        migration.verify_preflight_receipt(state / migration.PREFLIGHT_RECEIPT, plan)


def salt_layout(environment):
    state, plan, custody, live = environment
    recovery = live / "salts"
    replica = live / "replica"
    replica.mkdir()
    paths = {
        "identity-active": live / "active",
        "identity-salt-keyring": live / "keyring.yml",
        "identity-legacy-default": live / "legacy",
    }
    payload = {k: v for k, v in plan.items() if k != "plan_id"}
    contract = payload["config"]["secret_contract"]
    contract["identity_replica"] = str(replica)
    contract["items"] = contract["items"] + [
        {"kind": "data", "id": key, "path": str(path)} for key, path in paths.items()
    ]
    migration.atomic_json(
        state / "plan.json", payload | {"plan_id": migration.digest(payload)}
    )
    return state, custody, live, recovery, replica, paths


def test_a_salt_gone_with_traces_left_is_reported(environment):
    state, custody, _, recovery, _, paths = salt_layout(environment)
    (recovery / "enrolled").write_text("receipt")
    paths["identity-salt-keyring"].write_text("schema_version: 1\n")
    found = preflight.orphaned_salt(state, custody)
    assert found["active"] == str(paths["identity-active"])
    assert str(recovery / "enrolled") in found["traces"]
    assert found["copy"] is None


def test_a_custody_copy_of_the_lost_salt_is_found_and_restored(environment):
    state, custody, _, recovery, _, paths = salt_layout(environment)
    (recovery / "enrolled").write_text("receipt")
    copy = copy_of(custody, paths["identity-active"])
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text("saved")
    found = preflight.orphaned_salt(state, custody)
    assert found["copy"] == copy
    preflight.restore_salt(found["copy"], found["active"])
    assert paths["identity-active"].read_text() == "saved"
    assert preflight.orphaned_salt(state, custody) is None


@pytest.mark.parametrize("kept", ["active", "salts/active.salt", "replica/active.salt"])
def test_any_surviving_copy_is_not_an_orphan(environment, kept):
    # The provisioner recovers the salt itself from any of these.
    state, custody, live, recovery, _, _ = salt_layout(environment)
    (recovery / "enrolled").write_text("receipt")
    (live / kept).write_text("salt")
    assert preflight.orphaned_salt(state, custody) is None


def test_no_traces_is_a_fresh_host_not_an_orphan(environment):
    state, custody, *_ = salt_layout(environment)
    assert preflight.orphaned_salt(state, custody) is None


def test_a_center_host_is_left_to_vault(environment):
    state, custody, _, _, _, paths = salt_layout(environment)
    paths["identity-salt-keyring"].write_text("center_id: example\n")
    assert preflight.orphaned_salt(state, custody) is None


def test_setting_aside_moves_and_never_deletes(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "root_prefix", list)
    trace = tmp_path / "enrolled"
    trace.write_text("receipt")
    moved = preflight.set_aside([str(trace)])
    assert not trace.exists()
    assert Path(moved[0]).read_text() == "receipt"

