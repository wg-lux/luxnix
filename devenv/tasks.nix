
{pkgs,...}: {

  "initialize-environment:endoreg-db" = {
    description = "Initialize endoreg-db by running tasks 'endoreg-db:init' and 'endoreg-db:migrate'";
    # Trigger endoreg-db:init and endoreg-db:migrate
    exec = "devenv tasks run endoreg-db:init && devenv tasks run endoreg-db:migrate";
  };

  "initialize-environment:finished" = {
    description = "If called, this task triggers the ";
    exec = "echo 'Initialized Development & Administration Environment'";
    after = [ "initialize-environment:endoreg-db"];
  };

  "autoconf:generate-hostinfo" = {
      description = "Generate conf/hostinfo.json; Generates hostinfo @ ./docs/hostinfo (summary markdown; html split by host)";
      exec = "./scripts/ansible-cmdb.sh";
    };
  "autoconf:initialize-vault" = {
      description = "Initialize vault";
      exec = "${pkgs.uv}/bin/uv run python scripts/bootstrap-lx-vault.py";
  };

  "autoconf:build-nix-system-configs" = {
      description = "Build nix system configs";
      exec = "bnsc";
      # after = [ "autoconf:generate-hostinfo"];
    };

  # devenv run tasks autoconf:finished
  "autoconf:finished" = {
    description = "Start the finalize task";
    exec = "echo 'Starting finalize task'";
    after = [ "autoconf:build-nix-system-configs"];
  };

  # --- secrets stick ---
  "secrets:check-stick" = {
    description = "Verify the secrets stick is mounted and its layout is complete";
    exec = "${pkgs.uv}/bin/uv run python scripts/lx-secrets.py stick check";
  };

  "secrets:backup-stick" = {
    description = "Create a timestamped backup archive on the secrets stick";
    exec = "${pkgs.uv}/bin/uv run python scripts/lx-secrets.py stick backup";
  };

  "secrets:sync-inventory" = {
    description = "Sync public keys from stick to ansible/inventory/group_vars/stick_pubkeys.yml";
    exec = "${pkgs.uv}/bin/uv run python scripts/lx-secrets.py identity sync-inventory";
  };

  "secrets:vault-status" = {
    description = "Show what is staged in ~/.lxv/deploy/ per hostname";
    exec = "${pkgs.uv}/bin/uv run python scripts/lx-secrets.py vault status";
  };

  "secrets:stage-ssl" = {
    description = "Stage SSL cert (endo-reg.net) from stick for all [ssl_cert] hosts";
    exec = "${pkgs.uv}/bin/uv run python scripts/lx-secrets.py vault stage-ssl-group endo-reg.net ssl_cert";
  };

  "secrets:stage-keycloak-admin" = {
    description = "Generate keycloak_admin password on stick and stage it for h-01 (vault-encrypted)";
    exec = ''
      set -euo pipefail
      ${pkgs.uv}/bin/uv run python scripts/lx-secrets.py user set-password --username keycloak_admin --generate
      ${pkgs.uv}/bin/uv run python scripts/lx-secrets.py vault stage-keycloak-admin --hostname h-01
    '';
  };

  "docs:toc-generator" = {
    description = "Updating the documentation overview in TABLE OF CONTENTS";
    exec =  "${pkgs.uv}/bin/uv run python lib/toc-generator/generate-toc.py";
  };

  "docs:systems" = {
    description = "Regenerate docs/systems.md from autoconf/merged_vars and systems/ configs";
    exec = "${pkgs.uv}/bin/uv run python scripts/generate-systems-doc.py";
    after = [ "autoconf:build-nix-system-configs" ];
  };
  "endoreg-db:init" = {
    description = "Initializing endoreg-db module";
    exec = "./lib/endoreg-db/init.sh";
  };
  "endoreg-db:migrate" = {
      description = "Migrating the database of endoreg-db";
      exec = "./lib/endoreg-db/migrate.sh";
    };

}
