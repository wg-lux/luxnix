{ pkgs, ... }:
{
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
