{ pkgs, ... }:
{
  # Configuration and validation
  bnsc.package = pkgs.zsh;
  bnsc.exec = "devenv tasks run autoconf:generate";

  vault-bootstrap.package = pkgs.zsh;
  vault-bootstrap.exec = ''${pkgs.uv}/bin/uv run python scripts/bootstrap-lx-vault.py "$@"'';

  validate-admin-passwords.package = pkgs.zsh;
  validate-admin-passwords.exec = ''${pkgs.uv}/bin/uv run python scripts/validate-admin-passwords.py "$@"'';

  vault-site-preflight.package = pkgs.zsh;
  vault-site-preflight.exec = ''${pkgs.uv}/bin/uv run python scripts/vault/site_enrollment_preflight.py "$@"'';

  # Remote operations
  check-connectivity.package = pkgs.zsh;
  check-connectivity.exec = ''./scripts/check-connectivity.sh "$@"'';

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
  mount-persisting-storage.package = pkgs.zsh;
  mount-persisting-storage.exec = ''
    secretspec run --provider dotenv \
      uv run python scripts/storage/mount_persisting_storage.py
  '';
}
