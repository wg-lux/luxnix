{ config, lib, ... }:

let
  cfg = config.profiles.endoregStorageNode;
in
{
  options.profiles.endoregStorageNode.enable = lib.mkEnableOption "reusable defaults for a dedicated LX-Annotate storage-node host";

  config = lib.mkIf cfg.enable {
    roles = {
      aglnet.client.enable = lib.mkDefault true;
      base-server.enable = lib.mkDefault true;
      common.enable = lib.mkDefault true;
      custom-packages.enable = lib.mkDefault true;
    };

    services.luxnix.hubStorage.node.enable = lib.mkDefault true;
  };
}
