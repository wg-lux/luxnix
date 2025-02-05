{ lib ? <nixpkgs/lib> , ... }:
let
    base = import ./base.nix { inherit lib; }; 

    main = {
        secrets = import ./secrets.nix { inherit lib; };
        virtualHosts = import ./virtual-hosts.nix { inherit lib; };
    } // base;


in main