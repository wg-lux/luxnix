
{
  "autoconf:generate-hostinfo" = {
      description = "Generate conf/hostinfo.json; Generates hostinfo @ ./docs/hostinfo (summary markdown; html split by host)";
      exec = "./scripts/ansible-cmdb.sh";
    };

  "autoconf:build-nix-system-configs" = {
      description = "Build nix system configs";
      exec = "bnsc";
      after = [ "autoconf:generate-hostinfo"];
    };

  # devenv run tasks autoconf:finished
    "autoconf:finished" = {
      description = "Start the finalize task";
      exec = "echo 'Starting finalize task'";
      after = [ "autoconf:build-nix-system-configs"];
    };
  
  "docs:toc-generator" = {
    description = "Updating the documentation overview in TABLE OF CONTENTS";
    exec =  "./lib/toc-generator/toc.sh";
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
