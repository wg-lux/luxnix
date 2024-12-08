
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