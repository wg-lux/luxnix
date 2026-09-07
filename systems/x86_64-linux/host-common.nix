_:

# Shared baseline for Autoconf-managed NixOS hosts. Hardware, disk, boot,
# network, and service choices stay in each host entry point.
{
  user = {
    admin.name = "admin";
    ansible.enable = true;
    settings.mutable = false;
  };
}
