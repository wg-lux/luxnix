{
  pkgs,
  lib,
  env,
  isDev ? false,
}:
{
  hello.package = pkgs.zsh;
  bnsc.package = pkgs.zsh;
  blxv.package = pkgs.zsh;
  run-ansible.package = pkgs.zsh;
  ssh-all.package = pkgs.zsh;
  init-server-ssh.package = pkgs.zsh;
  kill-server-ssh.package = pkgs.zsh;
  conn-server-ssh.package = pkgs.zsh;
  sync-secrets.package = pkgs.zsh;
  create-ed25519-keypair.package = pkgs.zsh;
  hello.exec = "${pkgs.uv}/bin/uv run python hello.py";
  ac.package = pkgs.zsh;
  ensure-ansible-config.package = pkgs.zsh;

  utest.package = pkgs.zsh;
  utest.exec = "${pkgs.uv}/bin/uv run python -m unittest";
  initialize-luxnix-repo.exec = ''
    direnv allow
    touch .repo_initialized
  '';

  # Make sure ./conf/ansible.cfg exists, if not, create it by copying .conf/TEMPLATE_ansible.cfg

  ensure-ansible-config.exec = "cp -n ./conf/TEMPLATE_ansible.cfg ./conf/ansible.cfg";

  ac.exec = "devenv tasks run autoconf:finished";

  # hi.exec = "${pkgs.uv}/bin/uv run python lx_administration/ansible/hostinfo.py";

  bnsc.exec = "${pkgs.uv}/bin/uv run python scripts/autoconf-pipeline.py";
  blxv.exec = ''${pkgs.uv}/bin/uv run python scripts/bootstrap-lx-vault.py "$@"'';

  # lx-secrets: the secrets-stick CLI, available as `lx-secrets <command>` inside devenv shell
  lx-secrets.package = pkgs.zsh;
  lx-secrets.exec = ''${pkgs.uv}/bin/uv run python scripts/lx-secrets.py "$@"'';

  vault-bootstrap.package = pkgs.zsh;
  vault-bootstrap.exec = ''${pkgs.uv}/bin/uv run python scripts/bootstrap-lx-vault.py "$@"'';
  validate-admin-passwords.package = pkgs.zsh;
  validate-admin-passwords.exec = ''${pkgs.uv}/bin/uv run python scripts/validate-admin-passwords.py "$@"'';
  check-connectivity.package = pkgs.zsh;
  check-connectivity.exec = ''./scripts/check-connectivity.sh "$@"'';

  run-ansible.exec = "${pkgs.uv}/bin/uv run ansible-playbook ansible/site.yml";

  ssh-all.exec = "./tmux/all-luxnix-dir.sh";

  init-server-ssh.exec = "./tmux/init-server-ssh.sh";
  kill-server-ssh.exec = "tmux kill-session -t ssh-servers";
  conn-server-ssh.exec = "tmux attach-session -t ssh-servers";

  sync-secrets.exec = "ansible-playbook ./ansible/playbooks/deploy_secrets.yml";

  #WARNING: This will overwrite the existing ssh keys
  create-ed25519-keypair.exec = ''
    # warn user and ask whether to proceed
    echo "This will overwrite the existing ssh keys. Do you want to proceed? (y/n)"
    read proceed
    if [ "$proceed" != "y" ]; then
      echo "Aborted"
      exit 1
    fi
    # get hostname from env var
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -C "admin@$hostname"

    chmod 600 ~/.ssh/id_ed25519
    chmod 644 ~/.ssh/id_ed25519.pub
  '';

  # Mounting scripts
  mount-persisting-storage.package = pkgs.zsh;
  mount-persisting-storage.exec = ''
    secretspec run --provider dotenv \
      uv run python scripts/storage/mount_persisting_storage.py

  '';

  # ── Migration scripts ────────────────────────────────────────────────────────
  # Phase 1: copy VPN cert material from s-01 to h-01
  # Usage: devenv run migrate-vpn-certs [s01-host] [h01-host]
  migrate-vpn-certs.package = pkgs.zsh;
  migrate-vpn-certs.exec = ''./scripts/migration/vpn-certs-copy.sh "$@"'';

  # Phase 1: cut over gc-* GPU clients to h-01 VPN, one at a time
  # Run AFTER vpn.endo-reg.net DNS has been updated to h-01
  # Usage: devenv run vpn-client-rollout
  vpn-client-rollout.package = pkgs.zsh;
  vpn-client-rollout.exec = ''./scripts/migration/vpn-client-rollout.sh "$@"'';

  # Phase 2: full Keycloak + postgres data migration from s-02 to h-01
  # Usage: devenv run migrate-keycloak [--skip-deploy]
  migrate-keycloak.package = pkgs.zsh;
  migrate-keycloak.exec = ''./scripts/migration/keycloak-migrate.sh "$@"'';

  # Phase 5 (future): Nextcloud migration from s-03 to a new host
  # Usage: devenv run migrate-nextcloud <new-host-ip> [--skip-deploy]
  migrate-nextcloud.package = pkgs.zsh;
  migrate-nextcloud.exec = ''./scripts/migration/nextcloud-migrate.sh "$@"'';

}
