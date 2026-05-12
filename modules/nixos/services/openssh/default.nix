{
  config,
  lib,
  pkgs,
  ...
}:
#CHANGEME 
with lib;
with lib.luxnix; let
  cfg = config.services.ssh;
  hostname = config.networking.hostName;
  hostNetwork = config.luxnix.generic-settings.network.hosts.${hostname} or {};
  hostVpnIp = hostNetwork."ip-vpn" or null;
  aglnetClient = config.roles.aglnet.client or {};
  aglnetHost = config.roles.aglnet.host or {};
  defaultVpnDev =
    if (aglnetClient.enable or false)
    then aglnetClient.dev
    else if (aglnetHost.enable or false)
    then aglnetHost.dev
    else "tun";
  defaultVpnInterface = "${defaultVpnDev}0";
  defaultHostAliases =
    unique
    ([
        hostname
        "${hostname}.intern"
      ]
      ++ optional (hostVpnIp != null) hostVpnIp);

  registryLines =
    splitString "\n" (builtins.readFile cfg.hostIdentity.registryFile);
  splitFields = line: filter (part: part != "") (splitString " " line);
  registryEntries =
    map
    (line: let
      fields = splitFields line;
    in {
      names = splitString "," (elemAt fields 0);
      keyType = elemAt fields 1;
      key = elemAt fields 2;
    })
    (filter
      (line:
        line != ""
        && !(hasPrefix "#" line)
        && length (splitFields line) >= 3)
      registryLines);
  matchingEd25519Entries =
    filter
    (entry:
      entry.keyType == "ssh-ed25519"
      && any (alias: elem alias entry.names) cfg.hostIdentity.aliases)
    registryEntries;
  registryEd25519PublicKey =
    if matchingEd25519Entries == []
    then null
    else let
      entry = head matchingEd25519Entries;
    in "${entry.keyType} ${entry.key}";
  expectedEd25519PublicKey = cfg.hostIdentity.expectedEd25519PublicKey;
  hasExpectedEd25519PublicKey = expectedEd25519PublicKey != null;
  hostKeyGuardScript = strictMissing: ''
    expected='${expectedEd25519PublicKey}'
    key_file=/etc/ssh/ssh_host_ed25519_key.pub

    if [ ! -f "$key_file" ]; then
      echo "Luxnix SSH host-key guard: missing $key_file"
      ${if strictMissing then "exit 1" else "exit 0"}
    fi

    actual="$(${pkgs.coreutils}/bin/cut -d ' ' -f 1,2 "$key_file")"
    if [ "$actual" != "$expected" ]; then
      expected_fingerprint="$(printf '%s\n' "$expected" | ${pkgs.openssh}/bin/ssh-keygen -lf - 2>/dev/null | ${pkgs.coreutils}/bin/cut -d ' ' -f 2 || true)"
      actual_fingerprint="$(${pkgs.openssh}/bin/ssh-keygen -lf "$key_file" 2>/dev/null | ${pkgs.coreutils}/bin/cut -d ' ' -f 2 || true)"
      echo "Luxnix SSH host-key guard: ed25519 host key mismatch for ${hostname}" >&2
      echo "Registry: ${toString cfg.hostIdentity.registryFile}" >&2
      echo "Expected fingerprint: ''${expected_fingerprint:-unavailable}" >&2
      echo "Actual fingerprint:   ''${actual_fingerprint:-unavailable}" >&2
      echo "Update the registry only after out-of-band verification." >&2
      ${if cfg.hostIdentity.allowRotation then "echo \"Host-key rotation override is enabled; continuing.\" >&2" else "exit 1"}
    fi
  '';
in {
  options.services.ssh = with types; {
    enable = mkBoolOpt false "Enable ssh";
    authorizedKeys = mkOpt (listOf str) [] "The public keys to grant access to connect as admin.";
    network = {
      vpnInterface = mkOpt str defaultVpnInterface "VPN interface allowed to receive inbound SSH.";
    };
    forwarding = {
      allowTcp = mkBoolOpt false "Allow SSH TCP forwarding.";
      allowAgent = mkBoolOpt false "Allow SSH agent forwarding.";
      gatewayPorts = mkOpt (enum ["yes" "no" "clientspecified"]) "no" "GatewayPorts value when TCP forwarding is enabled.";
    };
    hostIdentity = {
      enable = mkBoolOpt true "Guard and persist this host's SSH host identity.";
      allowRotation = mkBoolOpt false "Allow a local SSH host key mismatch while intentionally rotating keys.";
      registryFile = mkOpt path ../../../../conf/ssh-host-keys/known_hosts "Tracked public SSH host-key registry.";
      aliases = mkOpt (listOf str) defaultHostAliases "Host aliases that must resolve to this machine's SSH host key.";
      expectedEd25519PublicKey = mkOpt (nullOr str) registryEd25519PublicKey "Expected ssh-ed25519 host public key, usually read from the registry.";
    };
  };

  config = mkIf cfg.enable {
    services.openssh = {
      enable = true;
      openFirewall = false;
      ports = [22];

      settings = {
        AllowAgentForwarding = cfg.forwarding.allowAgent;
        AllowTcpForwarding = if cfg.forwarding.allowTcp then "yes" else "no";
        AllowUsers = [config.user.admin.name];
        GatewayPorts = cfg.forwarding.gatewayPorts;
        KbdInteractiveAuthentication = false;
        PasswordAuthentication = false;
        PermitRootLogin = "no";
        StreamLocalBindUnlink = "yes";
        X11Forwarding = false;
      };
    };

    networking.firewall.interfaces.${cfg.network.vpnInterface}.allowedTCPPorts = [22];

    users.users = {
      ${config.user.admin.name}.openssh.authorizedKeys.keys = cfg.authorizedKeys;
    };

    programs.ssh.knownHostsFiles = [
      cfg.hostIdentity.registryFile
    ];

    system.activationScripts.luxnixSshHostKeyGuard = mkIf (cfg.hostIdentity.enable && hasExpectedEd25519PublicKey) {
      text = hostKeyGuardScript false;
    };

    systemd.services.sshd.preStart = mkIf (cfg.hostIdentity.enable && hasExpectedEd25519PublicKey) (mkAfter (hostKeyGuardScript true));

    warnings =
      optional (cfg.hostIdentity.enable && !hasExpectedEd25519PublicKey)
      "Luxnix SSH host-key guard for ${hostname} has no registry-derived ed25519 key; sshd preStart identity enforcement is inactive until ${toString cfg.hostIdentity.registryFile} is updated.";
  };
}
