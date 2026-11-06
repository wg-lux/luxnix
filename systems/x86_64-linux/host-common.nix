_:

# Shared baseline for Autoconf-managed NixOS hosts. Hardware, disk, boot,
# network, and service choices stay in each host entry point.
{
  user = {
    admin.name = "admin";
    ansible.enable = true;
    settings.mutable = false;
  };

  # Do not pull the `doc` output of every packaged program into the system
  # profile. It roughly doubles the closure for little benefit on these hosts,
  # and on nixos-26.05 the Python 3.12 `doc` build is broken upstream
  # (Sphinx/docutils), which would fail every `nixos-rebuild`. Man pages and
  # `info` are unaffected.
  documentation.doc.enable = false;
}
