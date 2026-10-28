{ lib, ... }:
{
  # Preserve the old public switch while keeping all behavior in one module.
  imports = [
    (lib.mkRenamedOptionModule
      [ "services" "virtualisation" "podman" "enable" ]
      [ "services" "luxnix" "podman" "enable" ]
    )
  ];
}
