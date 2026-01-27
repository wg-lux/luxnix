{ lib }:
with lib;
{
  url = mkOption {
    type = types.str;
    default = "https://github.com/wg-lux/endo-api";
    description = "Git repository URL for the Django API";
  };

  branch = mkOption {
    type = types.str;
    default = "main";
    description = "Git branch to checkout";
  };

  updateOnBoot = mkOption {
    type = types.bool;
    default = true;
    description = "Whether to update the repository on service start";
  };
}
