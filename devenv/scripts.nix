{ pkgs, ... }:
{
  # Configuration and validation
  check-secret-rotation.package = pkgs.zsh;
  check-secret-rotation.exec = ''${pkgs.uv}/bin/uv run python scripts/check-secret-rotation.py "$@"'';

  bnsc.package = pkgs.zsh;
  bnsc.exec = "devenv tasks run autoconf:generate";

  openbao-provision.package = pkgs.zsh;
  openbao-provision.exec = ''${pkgs.uv}/bin/uv run python -m lx_administration.storage.bao_migration "$@"'';

  vault-bootstrap.package = pkgs.zsh;
  vault-bootstrap.exec = ''${pkgs.uv}/bin/uv run python scripts/bootstrap-lx-vault.py "$@"'';

  validate-admin-passwords.package = pkgs.zsh;
  validate-admin-passwords.exec = ''${pkgs.uv}/bin/uv run python scripts/validate-admin-passwords.py "$@"'';

  vault-site-preflight.package = pkgs.zsh;
  vault-site-preflight.exec = ''${pkgs.uv}/bin/uv run python scripts/vault/site_enrollment_preflight.py "$@"'';

  # Remote operations
  check-connectivity.package = pkgs.zsh;
  check-connectivity.exec = ''./scripts/check-connectivity.sh "$@"'';

  storage-readiness.package = pkgs.zsh;
  storage-readiness.exec = ''
    ANSIBLE_CONFIG=conf/connectivity-ansible.cfg ANSIBLE_HOST_KEY_CHECKING=True LUXNIX_UV_BIN=${pkgs.uv}/bin/uv \
      bash scripts/run-ansible-playbook.sh ansible/playbooks/storage-readiness.yml \
      -i ansible/inventory/hosts.ini "$@"
  '';

  lx-annotate-streamable-migration.package = pkgs.zsh;
  lx-annotate-streamable-migration.exec = ''./scripts/lx-annotate-streamable-migration.sh "$@"'';

  run-ansible.package = pkgs.zsh;
  run-ansible.exec = ''
    LUXNIX_UV_BIN=${pkgs.uv}/bin/uv \
      bash scripts/run-ansible-playbook.sh ansible/site.yml "$@"
  '';

  sync-secrets.package = pkgs.zsh;
  sync-secrets.exec = ''
    LUXNIX_UV_BIN=${pkgs.uv}/bin/uv \
      bash scripts/run-ansible-playbook.sh \
      ansible/playbooks/deploy_secrets.yml "$@"
  '';

  rotate-admin-passwords.package = pkgs.zsh;
  rotate-admin-passwords.exec = ''
    ANSIBLE_HOST_KEY_CHECKING=True LUXNIX_UV_BIN=${pkgs.uv}/bin/uv \
      bash scripts/run-secret-playbook.sh ansible/playbooks/rotate_admin_passwords.yml "$@"
  '';

  rotate-hub-enrollment.package = pkgs.zsh;
  rotate-hub-enrollment.exec = ''
    ANSIBLE_HOST_KEY_CHECKING=True LUXNIX_UV_BIN=${pkgs.uv}/bin/uv \
      bash scripts/run-secret-playbook.sh ansible/playbooks/rotate_hub_enrollment.yml "$@"
  '';

  enroll-reachable-hub-sites.package = pkgs.zsh;
  enroll-reachable-hub-sites.exec = ''
    LUXNIX_UV_BIN=${pkgs.uv}/bin/uv bash scripts/enroll-reachable-hub-sites.sh "$@"
  '';

  deliver-hub-enrollment.package = pkgs.zsh;
  deliver-hub-enrollment.exec = ''
    ANSIBLE_HOST_KEY_CHECKING=True LUXNIX_UV_BIN=${pkgs.uv}/bin/uv \
      bash scripts/run-secret-playbook.sh ansible/playbooks/deliver_hub_enrollment.yml "$@"
  '';

  secure-boot-keys.package = pkgs.zsh;
  secure-boot-keys.exec = ''${pkgs.uv}/bin/uv run python -m lx_administration.secure_boot create-keys "$@"'';

  secure-boot-sign.package = pkgs.zsh;
  secure-boot-sign.exec = ''${pkgs.uv}/bin/uv run python -m lx_administration.secure_boot sign "$@"'';

  vault-migrate-local-key.package = pkgs.zsh;
  vault-migrate-local-key.exec = ''${pkgs.uv}/bin/uv run python scripts/vault/migrate_local_key.py "$@"'';

  # SSH session management
  ssh-all.package = pkgs.zsh;
  ssh-all.exec = ''${pkgs.uv}/bin/uv run python scripts/tmux-inventory-session.py workspace "$@"'';

  init-server-ssh.package = pkgs.zsh;
  init-server-ssh.exec = ''${pkgs.uv}/bin/uv run python scripts/tmux-inventory-session.py monitor "$@"'';

  kill-server-ssh.package = pkgs.zsh;
  kill-server-ssh.exec = "tmux kill-session -t ssh-servers";

  conn-server-ssh.package = pkgs.zsh;
  conn-server-ssh.exec = "tmux attach-session -t ssh-servers";

  # Local storage
  storage-provision.package = pkgs.zsh;
  storage-provision.exec = ''${pkgs.uv}/bin/uv run python -m lx_administration.storage.provision "$@"'';
  openbao-local.package = pkgs.zsh;
  openbao-local.exec = ''${pkgs.uv}/bin/uv run python -m lx_administration.storage.local_enrollment "$@"'';
  mount-persisting-storage.package = pkgs.zsh;
  mount-persisting-storage.exec = ''
    secretspec run --provider dotenv \
      uv run python scripts/storage/mount_persisting_storage.py
  '';
}
