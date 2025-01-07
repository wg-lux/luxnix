{ pkgs, lib, config, inputs, ... }:
{
  tasks = {
    "autoconf:generate-hostinfo" = {
      description = "Generate conf/hostinfo.json; Generates hostinfo @ ./docs/hostinfo (summary markdown; html split by host)";
      exec = "./scripts/ansible-cmdb.sh";
      # after = [ "autoconf:setup-symlinks" ];
    };

    "autoconf:finished" = {
      description = "Start the finalize task";
      exec = "echo 'Starting finalize task'";
      after = [ "autoconf:generate-hostinfo" ];
    };
  };
}
