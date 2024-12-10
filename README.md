

# Identities

# Computer (auto generated on machine creation)
- /etc/machine-id
- ssh_host_ed25519_key
- ssh_host_rsa_key

## User
- ~/.ssh/id_ed25519 -> user@host
        - ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
        - You can add the key to git!


# SSH
- SSH is currently imported within the roles `gpu-client-dev` and `server`

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

# Certificate Authority


# GC 07
nixos-anywhere --flake '.#gc-03' nixos@192.168.0.48