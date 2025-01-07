{ pkgs, lib, config, inputs, ... }:
{
  scripts = {
    hello.exec = "${pkgs.uv}/bin/uv run python hello.py";
    utest.exec = "${pkgs.uv}/bin/uv run python -m unittest";

    initialize-luxnix-repo.exec = ''
      direnv allow
      touch .repo_initialized
    '';

    hi.exec = "${pkgs.uv}/bin/uv run python lx_administration/ansible/hostinfo.py";
    bnsc.exec = "${pkgs.uv}/bin/uv run python scripts/build-nix-system-configs.py";
    
    run-ansible.exec = "${pkgs.uv}/bin/uv run ansible-playbook ansible/site.yml";
    
    ssh-all.exec = "./tmux/all-luxnix-dir.sh";
    init-server-ssh.exec = "./tmux/init-server-ssh.sh";
    kill-server-ssh.exec = "tmux kill-session -t ssh-servers";
    conn-server-ssh.exec = "tmux attach-session -t ssh-servers";
  };
}
