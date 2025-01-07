{ pkgs, ... }: {
  #services.endoreg_db = {
  #  enable = true;

  services = {
    services.endoreg_db = {
      enable = true;
    };
  }
}
