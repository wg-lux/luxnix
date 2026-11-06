"""Choose how a host gets its identity salt, before the encryption plan pins a revision.

The recommended salt is random, created by the host and kept only there, so the hub
cannot reverse the pseudonyms it receives. A center salt from gs-02's Vault is kept only
for hosts already configured for one; it is not offered as a new choice. Choices go into
the host inventory through an Ansible playbook, so they exist in Git before anything is
pinned. Salt values are never read or printed.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import NoReturn

import yaml

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import secret_preflight
from lx_administration.storage.boot_migration import Stopped
from lx_administration.storage.boot_setup import success
from lx_administration.yaml import load_unique_yaml_file

PLAYBOOK = Path("ansible/playbooks/first-setup-config.yml")
DJANGO = "luxnix.lxAnnotateLocal.django"
ACTIVATION_GUIDE = "docs/center-identity-salt-activation.md"
VAULT_HEALTH = {
    "200": "ready",
    "429": "ready (standby)",
    "501": "NOT INITIALIZED",
    "503": "SEALED",
}
EVALUATION = """
let
  f = builtins.getFlake CHECKOUT;
  c = f.nixosConfigurations.HOST.config;
  server = f.nixosConfigurations.gs-02.config;
  hub = server.services.luxnix.lxAnnotateLocal.hub.nodeProvisioning.nodes;
  node = builtins.filter (n: n.nodeKey == "HOST") hub;
  # Only a center host depends on gs-02; lazy, so others never evaluate it.
  usesHub = (c.services.luxnix.lxAnnotateLocal.enable or false)
    && c.services.luxnix.lxAnnotateLocal.django.centerIdentitySalt;
in {
  enabled = c.services.luxnix.lxAnnotateLocal.enable or false;
  center = c.services.luxnix.lxAnnotateLocal.django.centerIdentitySalt;
  legacy = c.services.luxnix.lxAnnotateLocal.django.enrollLegacyDefaultSalt;
  create = c.services.luxnix.lxAnnotateLocal.django.createInitialIdentitySalt;
  keyring = c.services.luxnix.lxAnnotateLocal.django.identitySaltKeyringFile;
  vault_dir = c.luxnix.vault.dir;
  center_key = c.roles.endoreg-client.defaultCenterKey or null;
  vault_address = c.luxnix.vault.client.address;
  vault_ca = c.luxnix.vault.client.caCertFile;
  centers =
    if usesHub then server.luxnix.vault.server.hubPki.sharedIdentityCenters else [ ];
  node_center =
    if usesHub && node != [ ] then (builtins.head node).centerKey or null else null;
  listed = usesHub && node != [ ];
}
"""


@dataclass(frozen=True)
class Choice:
    center: str | None  # None means this host's own machine salt.
    legacy: bool


OWN_SALT = Choice(center=None, legacy=True)
ESTABLISHED, NO_SALT, UNKNOWN = "established", "none", "unknown"


def evaluate(checkout: Path, host: str) -> dict:
    expression = EVALUATION.replace(
        "CHECKOUT", json.dumps(f"git+file://{checkout}")
    ).replace("HOST", host)
    result = subprocess.run(
        ["nix", "eval", "--no-update-lock-file", "--impure", "--json", "--expr",
         expression],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=600,
        check=False,
    )  # fmt: skip
    if result.returncode:
        raise migration.MigrationError(
            f"{host} must evaluate before first setup, and gs-02 too on a center salt"
        )
    return json.loads(result.stdout)


def read_keyring(facts: dict) -> tuple[str, dict | None]:
    """Report what is known; the manifest holds only paths, never salt values.

    An unreadable or empty secrets directory is not proof that no salt exists, so it
    is UNKNOWN. That locks only the irreversible change, never keeping the setting.
    """
    if facts["keyring"]:
        result = secret_preflight.privileged("cat", facts["keyring"])
        if result.returncode == 0:
            try:
                return ESTABLISHED, yaml.safe_load(result.stdout)
            except yaml.YAMLError:
                return UNKNOWN, None
    listing = secret_preflight.privileged(
        "find", facts["vault_dir"], "-mindepth", "1", "-maxdepth", "1", "-print"
    )
    if listing.returncode or not listing.stdout.strip():
        return UNKNOWN, None
    return NO_SALT, None


def center_salt_delivered(center: str, vault_dir: str) -> bool:
    directory = Path(vault_dir)
    return secret_preflight.exists(
        directory / f"lx_annotate_center_{center}_identity"
    ) or secret_preflight.exists(directory / f"lx_annotate_identity_center_{center}")


def vault_status(address: str, certificate: str | None) -> str:
    """Ask the unauthenticated health endpoint; no token and no secret is involved."""
    command = ["curl", "-sS", "-m", "5", "-o", "/dev/null", "-w", "%{http_code}"]
    if certificate and secret_preflight.exists(Path(certificate)):
        command += ["--cacert", certificate]
    try:
        result = secret_preflight.privileged(*command, f"{address}/v1/sys/health")
    except subprocess.SubprocessError:
        return "not reachable from here"
    return VAULT_HEALTH.get(result.stdout.decode().strip(), "not reachable from here")


def refusal(choice: Choice, keyring: dict | None) -> str | None:
    """Explain why a choice would stop LX-Annotate; a switched salt cannot go back."""
    if keyring is None:
        return None
    active_center = keyring.get("center_id")
    if active_center and choice.center != active_center:
        return (
            f"This host already uses the {active_center} center salt, and there is no "
            "supported way back or to another center: LX-Annotate would stay stopped"
        )
    if keyring.get("allow_legacy_default_salt") and not choice.legacy:
        return (
            "This host already reads the legacy default salt; turning that off would "
            "stop LX-Annotate"
        )
    return None


def center_problem(host: str, center: str, facts: dict) -> str | None:
    if center not in facts["centers"]:
        return f"{center} is not opted in on gs-02; see {ACTIVATION_GUIDE}"
    if not facts["listed"]:
        return f"{host} is not a provisioned node on gs-02; see {ACTIVATION_GUIDE}"
    if facts["node_center"] != center:
        return (
            f"gs-02 lists {host} under {facts['node_center']}, not {center}, so it "
            f"would grant no access. See {ACTIVATION_GUIDE}"
        )
    return None


def current_choice(facts: dict) -> Choice:
    return Choice(
        center=facts["center_key"] if facts["center"] else None, legacy=facts["legacy"]
    )


def host_salt_settings(facts: dict, *, create: bool) -> list[dict]:
    """Settings for the host's own salt; the legacy option enables the salt unit."""
    wanted = {
        "centerIdentitySalt": ("false", facts["center"]),
        "enrollLegacyDefaultSalt": ("true", not facts["legacy"]),
        "createInitialIdentitySalt": ("true", create and not facts["create"]),
    }
    return [
        {"section": "host_services", "key": f"{DJANGO}.{name}", "value": value}
        for name, (value, needed) in wanted.items()
        if needed
    ]


def write_inventory(checkout: Path, host: str, settings: list[dict]) -> None:
    """Run the playbook away from ansible.cfg, whose vault keys hosts do not hold."""
    playbook = checkout / PLAYBOOK
    program = shutil.which("ansible-playbook")
    if program is None:
        raise migration.MigrationError(
            "ansible-playbook is missing; run this inside the Devenv shell"
        )
    with tempfile.NamedTemporaryFile("w", suffix=".json") as variables:
        json.dump({"target_host": host, "settings": settings}, variables)
        variables.flush()
        result = subprocess.run(
            [program, str(playbook), "-i", "localhost,", "-e", f"@{variables.name}"],
            cwd=playbook.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300,
            check=False,
        )
    if result.returncode:
        print(result.stdout)
        raise migration.MigrationError("The inventory playbook failed; see above")


def regenerate(checkout: Path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/autoconf-pipeline.py"],
        cwd=checkout,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode:
        print(result.stdout)
        raise migration.MigrationError(
            "Autoconf could not generate these choices; inventory stays as written, "
            "so review it with git diff"
        )


def describe(choice: Choice) -> str:
    salt = (
        f"center salt shared by {choice.center}, from gs-02's Vault"
        if choice.center
        else "random salt created and kept only by this host; the hub never holds it"
    )
    reader = "yes" if choice.legacy else "no"
    return f"{salt}\n  Reads old default_salt records: {reader}"


def show_status(
    host: str, choice: Choice, facts: dict, status: str, keyring: dict | None
) -> None:
    active = {
        NO_SALT: "none found",
        UNKNOWN: "cannot tell; storage may be locked",
        ESTABLISHED: (keyring or {}).get("center_id") or "this host's own salt",
    }[status]
    print(f"\n=== LuxNix first setup: {host} ===")
    print(f"Configured: {describe(choice)}")
    print(f"Active on this host: {active}")
    if choice.center:
        print(
            f"gs-02 Vault: {vault_status(facts['vault_address'], facts['vault_ca'])} "
            f"({facts['vault_address']})"
        )
        print(
            "A center salt is held in gs-02's Vault, so the hub operator could reverse "
            "the pseudonyms it receives. A host salt avoids that, but machines of the "
            "center no longer share patient identities."
        )


def move_to_host_salt(
    checkout: Path, host: str, facts: dict, *, create: bool
) -> NoReturn:
    """Write and verify the change, then pause; the plan pins the next commit."""
    path = checkout / "ansible/inventory/host_vars" / f"{host}.yml"
    load_unique_yaml_file(path)  # Refuse a missing or malformed inventory first.
    write_inventory(checkout, host, host_salt_settings(facts, create=create))
    regenerate(checkout)
    if current_choice(evaluate(checkout, host)) != OWN_SALT:
        raise migration.MigrationError(
            "The evaluated configuration differs from your choice; review git diff"
        )
    relative = path.relative_to(checkout)
    paths = f"{relative} systems/x86_64-linux/{host}"
    print(f"\nWritten to {relative} and regenerated. Now review and commit:")
    print(f"  git diff {paths}")
    print(f"  git add -A {paths}")
    print(f'  git commit -m "First setup: identity salt for {host}"')
    raise Stopped("The plan is created after this commit.")


def accept_data_loss(host: str, consequence: str) -> str:
    """Name who accepted it; this is the operator's decision, never a default."""
    print(f"\n{consequence}")
    phrase = f"ACCEPT DATA LOSS {host}"
    if input(f"Type {phrase} to accept this: ").strip() != phrase:
        raise Stopped("Nothing was accepted.")
    name = input("Name of the person accepting this: ").strip()
    if not name:
        raise Stopped("A named person must accept this.")
    return name


def require_delivery(host: str, center: str, vault_dir: str) -> str | None:
    """The site fails closed without its salt, so settle this before encrypting."""
    if center_salt_delivered(center, vault_dir):
        print(f"Center salt for {center} is present on this host.")
        return None
    print(
        f"\nThe {center} salt is not on this host yet. gs-02's Vault creates it once "
        "and grants this site access during enrollment. Without it, LX-Annotate will "
        "not start after encryption. From your controller, with Vault unsealed, run:\n"
        f"  devenv shell enroll-reachable-hub-sites --site {host}"
    )
    print(
        "1. It has finished successfully\n"
        "2. Continue without it\n"
        "3. Stop and run it first"
    )
    reply = input("> ").strip()
    if reply == "1":
        return None
    if reply != "2":
        raise Stopped("Run the enrollment first.")
    return accept_data_loss(
        host,
        "LX-Annotate stays stopped after encryption until this enrollment is done. "
        "If this host's other salts are also gone, records imported so far cannot be "
        "matched to their patients again.",
    )


def change_offered(
    choice: Choice, facts: dict, status: str, keyring: dict | None
) -> str | None:
    """Offer only what cannot stop the host; everything else stays on Keep."""
    if choice.center:
        if status == UNKNOWN:
            print(
                "Moving to this host's own salt is unavailable until storage is "
                "unlocked, because a salt already active here cannot be changed."
            )
            return None
        if refusal(OWN_SALT, keyring):
            return None
        return "Use this host's own random salt (recommended)"
    if status != ESTABLISHED and not facts["create"]:
        print(
            "If no salt comes back from custody, LX-Annotate waits until creating one "
            "is allowed."
        )
        return "Let this host create a random salt on first start (recommended)"
    return None


def run(checkout: Path, host: str, *, ask_delivery: bool = True) -> str | None:
    """Settle the choice; return who accepted continuing without the center salt."""
    if not migration.HOST.fullmatch(host):
        raise migration.MigrationError("Invalid inventory host name")
    print("Reading this host's configuration...")
    facts = evaluate(checkout, host)
    if not facts["enabled"]:
        print(f"LX-Annotate is not enabled on {host}, so it needs no salt choice.")
        return None
    status, keyring = read_keyring(facts)
    choice = current_choice(facts)
    show_status(host, choice, facts, status, keyring)
    problem = refusal(choice, keyring)
    if problem:
        raise migration.MigrationError(
            f"Inventory conflicts with this host: {problem}. Restore the inventory "
            f"setting that matches the active salt and rerun; see {ACTIVATION_GUIDE}"
        )
    change = change_offered(choice, facts, status, keyring)
    print("\n1. Keep this and continue")
    if change:
        print(f"2. {change}")
    print("3. Stop for now")
    answer = input("> ").strip()
    if answer == "2" and change:
        print(f"\nNew setting: {describe(OWN_SALT)}")
        move_to_host_salt(checkout, host, facts, create=status != ESTABLISHED)
    if answer != "1":
        raise Stopped("Nothing was changed.")
    accepted_by = None
    if choice.center and ask_delivery:
        problem = center_problem(host, choice.center, facts)
        if problem:
            raise migration.MigrationError(problem)
        accepted_by = require_delivery(host, choice.center, facts["vault_dir"])
    elif choice.center:
        print("Center salt delivery is checked when the plan is created.")
    success(f"First setup is settled for {host}: {describe(choice)}")
    return accepted_by
