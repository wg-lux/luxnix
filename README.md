
Acknowledgements:
- https://github.com/hmajid2301/nixicle 
- https://haseebmajid.dev/posts/2024-05-02-part-5b-installing-our-nix-configuration-as-part-of-your-workflow/


nixos-anywhere --flake '.#server-03' nixos@192.168.179.3

---
identities = {
        ed25519 = { # ed25519 keys
backup = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC/gVfFAeG/9CwqiPOxu5JoY/vx705a77wvGgh687a5d";
gpu-client-dev = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHwYnbv/tPCcTIPgFbOISXDOiGZGpyUtu6NmtJ+Pg9Dh agl-gpu-client-dev";
gpu-client-06 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMenwtVZxjgAWj6xKZqB40QTl9smUcaoDnTRmJ/icp29 lux@gc06";
        };
    };



# GC 07
nixos-anywhere --flake '.#gc-03' nixos@192.168.0.48

# Default User Setup

The Settings for the default browser are imported from the common user.
/home/admin/luxnix/modules/home/roles/common/default.nix

Firefox is the default browser. Its settings are located in:
/home/admin/luxnix/modules/home/browsers/firefox/default.nix

The default homepage ccan be specified in profiles.default.extraConfig