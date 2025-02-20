{ pkgs, ... }:
{

  hello.exec = "${pkgs.uv}/bin/uv run python hello.py";
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
  blxv.exec = "${pkgs.uv}/bin/uv run python scripts/bootstrap-lx-vault.py";

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

}
