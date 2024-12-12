# To-Do
- [ ] Migrate Tempfile Rules

# VPN Configuration
- defined in modules/nixos/vpn
- 

# Identities

## Computer (auto generated on machine creation)
- /etc/machine-id
- /etc/ssh/ssh_host_ed25519_key
- /etc/ssh/ssh_host_rsa_key

--> collect and store in luxnix-administration/data/computer-identities/{host}

## User
Manually deploy your personal ed_25519 key to
- ~/.ssh/id_ed25519
  - if you want, you can also generate a new one: ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
- You can add the key to git!

## OpenVPN 
! Manually deployed during system setup !

Clients require:
- private key (gc-01.key -> cert.key)
- certificate (gc-01.crt -> cert.crt)
- server certificate: ca.cert
- pre-shared key: ta.key

/etc/identity/openvpn/

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