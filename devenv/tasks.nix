{pkgs}: {
  tasks = {
    toc-generator = {
      enable = true;
      start = ''
        ../lib/toc-generator/bin/toc-generator
      '';
    };
  };
}