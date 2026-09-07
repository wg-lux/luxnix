from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_SHELL = REPO_ROOT / "modules/home/cli/shells/shared/default.nix"
ZSH_SHELL = REPO_ROOT / "modules/home/cli/shells/zsh/default.nix"
ALIAS_MODULES = tuple(
    path
    for path in sorted((REPO_ROOT / "modules/home").rglob("*.nix"))
    if "shellAliases = {" in path.read_text(encoding="utf-8")
)


def _shell_aliases(module: Path) -> set[str]:
    source = module.read_text(encoding="utf-8")
    alias_block = source.split("shellAliases = {", 1)[1].split("};", 1)[0]
    return set(re.findall(r"^\s*([a-z][a-z0-9-]*)\s*=", alias_block, re.MULTILINE))


def test_shared_and_zsh_specific_aliases_have_one_owner() -> None:
    shared_aliases = _shell_aliases(SHARED_SHELL)
    zsh_aliases = _shell_aliases(ZSH_SHELL)

    assert shared_aliases.isdisjoint(zsh_aliases)
    assert {"cleanup", "inspect-gcroots", "nho", "nhh"} <= shared_aliases
    assert {"show-auth-keys", "lx-monitor"} <= zsh_aliases
    assert "cfg.zsh.enable && cfg.shared.enable" in SHARED_SHELL.read_text(
        encoding="utf-8"
    )


def test_every_home_manager_alias_has_one_module_owner() -> None:
    owners: dict[str, list[str]] = {}
    for module in ALIAS_MODULES:
        for alias in _shell_aliases(module):
            owners.setdefault(alias, []).append(str(module.relative_to(REPO_ROOT)))

    duplicate_owners = {
        alias: modules for alias, modules in owners.items() if len(modules) > 1
    }
    assert ALIAS_MODULES
    assert not duplicate_owners


def test_shell_helpers_do_not_delete_gc_roots_or_print_managed_secrets() -> None:
    reviewed_files = [
        *ALIAS_MODULES,
        REPO_ROOT / "CommonErrors.md",
        REPO_ROOT / "LxCheatsheet.md",
    ]
    reviewed_text = "\n".join(
        path.read_text(encoding="utf-8") for path in reviewed_files
    )

    assert "cleanup-roots" not in reviewed_text
    assert "rm /nix/var/nix/gcroots" not in reviewed_text
    assert "SCRT_local_password_admin_password" not in reviewed_text
    assert "inspect-gcroots" in reviewed_text
