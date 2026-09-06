{ pkgs, ... }:
{
  # devenv runs `prek run -a` (every hook over every file) as part of
  # `devenv:enterShell --mode all` on every shell entry, because the built-in
  # `devenv:git-hooks:run` task is dependency-connected to `enterShell`. A
  # repo-wide lint sweep does not belong on `cd`: it is slow and it hard-blocks
  # the shell whenever the tree carries any pre-existing lint debt (which it
  # currently does, on `origin` too). Neutralise the entry-time run. The git
  # pre-commit hook installed by `devenv:git-hooks:install` still runs the same
  # ansible-lint and nix-quality checks against staged files on every real
  # commit, and running "prek run -a" by hand still performs the full sweep on
  # demand.
  "devenv:git-hooks:run".exec = pkgs.lib.mkForce "true";

  # Environment initialization
  "initialize-environment:endoreg-db" = {
    description = "Initialize and migrate the EndoReg database";
    exec = "devenv tasks run endoreg-db:init && devenv tasks run endoreg-db:migrate";
  };

  "initialize-environment:finished" = {
    description = "Confirm that development environment initialization finished";
    exec = "echo 'Initialized Development & Administration Environment'";
    after = [ "initialize-environment:endoreg-db" ];
  };

  # Autoconf and local inventory
  "autoconf:check" = {
    description = "Validate and show resolved options from autoconf/config.yml";
    exec = "${pkgs.uv}/bin/uv run python scripts/autoconf-pipeline.py --check";
  };

  "autoconf:refresh-facts" = {
    description = "Refresh local Ansible facts; retain last-known-good data for failed hosts";
    exec = "./scripts/refresh-ansible-facts.sh";
  };

  "autoconf:refresh-facts-strict" = {
    description = "Refresh local Ansible facts and fail if any inventory host is stale";
    exec = "./scripts/refresh-ansible-facts.sh --strict";
  };

  "autoconf:generate-report" = {
    description = "Generate a private, redacted HTML inventory report from local facts";
    exec = "${pkgs.uv}/bin/uv run python scripts/generate-cmdb-report.py";
  };

  "autoconf:initialize-vault" = {
    description = "Initialize the Autoconf vault";
    exec = "${pkgs.uv}/bin/uv run python scripts/bootstrap-lx-vault.py";
  };

  "autoconf:generate" = {
    description = "Validate Autoconf options and generate NixOS and Home Manager configs";
    exec = "${pkgs.uv}/bin/uv run python scripts/autoconf-pipeline.py";
    after = [ "autoconf:check" ];
  };

  # Documentation
  "docs:toc-generator" = {
    description = "Regenerate TABLE_OF_CONTENTS.md";
    exec = "${pkgs.uv}/bin/uv run python lib/toc-generator/generate-toc.py";
  };

  "docs:check" = {
    description = "Validate documentation navigation and portable local links";
    exec = "${pkgs.uv}/bin/uv run pytest -q tests/test_documentation_contract.py";
  };

  "tests:pytest" = {
    description = "Run the repository Python test suite";
    exec = "${pkgs.uv}/bin/uv run pytest -q";
  };

  # Nix quality
  "nix-quality:check" = {
    description = "Run fast Nix parse, deadnix, statix, nixfmt, and flake-checker checks";
    exec = "${pkgs.uv}/bin/uv run python scripts/nix-quality.py";
  };

  "nix-quality:generators" = {
    description = "Run the 61 non-evaluating Autoconf and boot-renderer quality contracts";
    exec = "${pkgs.uv}/bin/uv run pytest -q tests/test_autoconf_rendering.py tests/test_ansible_autoconf_nixos_config.py tests/test_autoconf_cli.py tests/test_boot_decryption_renderer.py";
  };

  "nix-quality:full" = {
    description = "Run Nix quality checks plus full flake evaluation";
    exec = "${pkgs.uv}/bin/uv run python scripts/nix-quality.py --full";
  };

  # EndoReg database
  "endoreg-db:init" = {
    description = "Initialize the EndoReg database";
    exec = "./lib/endoreg-db/init.sh";
  };

  "endoreg-db:migrate" = {
    description = "Migrate the EndoReg database";
    exec = "./lib/endoreg-db/migrate.sh";
  };
}
