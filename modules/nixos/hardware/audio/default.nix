{
  config,
  pkgs,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.hardware.audio;
in {
  options.hardware.audio = with types; {
    enable = mkBoolOpt true "Enable or disable hardware audio support";
  };

  config = mkIf cfg.enable {

  # Enable sound with pipewire.
  # sound.enable = false;
  # wireplumber.enable = true;
  services.pulseaudio.enable = false;
  security.rtkit.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
    # If you want to use JACK applications, uncomment this
    #jack.enable = true;

    # use the example session manager (no others are packaged yet so this is enabled by default,
    # no need to redefine it in your config for now)
    #media-session.enable = true;
    wireplumber.enable = true;

  };

  #   users.extraUsers.admin.extraGroups = [ "audio" ];
    users.users.admin.extraGroups = [ "audio" ];
  #   # hardware.pulseaudio.enable = false;
    # security.rtkit.enable = true;
  #   hardware.pulseaudio.enable = true;
  #   hardware.pulseaudio.support32Bit = true;    ##
  #   services.pipewire.enable=false;
  #   # services.pipewire = {
  #   #   enable = true;
  #   #   support32Bit = true;
  #   # #   alsa.enable = true;
  #   # #   alsa.support32Bit = true;
  #   # #   pulse.enable = true;
  #   # #   jack.enable = true;
  #   # #   wireplumber.enable = true;
  #   # };
  #   # programs.noisetorch.enable = true;

  #   services.udev.packages = with pkgs; [
  #     # headsetcontrol
  #   ];

    environment.systemPackages = with pkgs; [
      # headsetcontrol
      # headset-charge-indicator
      pavucontrol
      pulsemixer
    ];
  };
}
