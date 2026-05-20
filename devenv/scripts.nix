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
  vault-bootstrap.package = pkgs.zsh;
  vault-bootstrap.exec = ''${pkgs.uv}/bin/uv run python scripts/bootstrap-lx-vault.py "$@"'';
  validate-admin-passwords.package = pkgs.zsh;
  validate-admin-passwords.exec = ''${pkgs.uv}/bin/uv run python scripts/validate-admin-passwords.py "$@"'';
  check-connectivity.package = pkgs.zsh;
  check-connectivity.exec = ''./scripts/check-connectivity.sh "$@"'';
  lx-annotate-streamable-migration.package = pkgs.zsh;
  lx-annotate-streamable-migration.exec = ''
    set -euo pipefail

    usage() {
      cat <<'EOF'
Usage:
  lx-annotate-streamable-migration <host> [migrate_video_streamable_storage args...]

Examples:
  lx-annotate-streamable-migration gc-10 --video-id 34 --processed-only
  lx-annotate-streamable-migration gc-10 --dry-run --processed-only

This runs the deployed lx-annotate Django streamable migration helper on the
target host under endoreg-service-user. The target command rewrites streamable
artifacts through the application storage/decryption layer and atomically
replaces invalid encrypted streamable files.
EOF
    }

    if [ "$#" -lt 1 ] || [ "''${1:-}" = "-h" ] || [ "''${1:-}" = "--help" ]; then
      usage
      exit 0
    fi

    target_host="$1"
    shift

    ssh -t "$target_host" \
      sudo -u endoreg-service-user -g endoreg-service \
      /run/current-system/sw/bin/bash -lc \
      '"'"'
        set -euo pipefail
        source /nix/store/9drfjl9dbbnx9cw3mm2vkwv89b8z6w8s-lx-annotate-env-helpers.sh
        lx_annotate_export_wheel_service_env /var/lib/lx-annotate/data
        cd /var/endoreg-service-user/lx-annotate-wheel
        exec .venv/bin/python -m django migrate_video_streamable_storage \
          --settings=lx_annotate.settings.settings_prod "$@"
      '"'"' lx-annotate-streamable-migration "$@"
  '';

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



}
