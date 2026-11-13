{
  config,
  lib,
  ...
}:
# Role-derived client allowlists. Roles choose the tier; consumers such as
# early-boot unlock and the lx-annotate VPN restriction read the derived lists
# as their defaults. This module only declares options and emits no system
# configuration of its own.
let
  inherit (lib)
    concatMap
    literalExpression
    mkOption
    optional
    optionals
    types
    unique
    ;
  access = (import ../../../../lib/network-access { inherit lib; }).networkAccess;

  cfg = config.luxnix.networkAccess;
  settings = config.luxnix.generic-settings;
  hostMap = settings.network.hosts;
  ownCluster = (hostMap.${config.networking.hostName} or { }).network-cluster or null;

  hostEntry =
    name:
    hostMap.${name} or (throw (
      "luxnix.networkAccess: host '${name}' is not in luxnix.generic-settings.network.hosts; "
      + "add it to the Autoconf inventory host map."
    ));

  vpnSource =
    name:
    let
      address = (hostEntry name).ip-vpn;
    in
    if address == "172.16.255.x" then
      throw "luxnix.networkAccess: host '${name}' has no inventory VPN address."
    else
      access.hostCidr address;

  # Early boot runs before the VPN, so only LAN addresses in this host's own
  # network cluster can reach it. Hosts elsewhere are deliberately skipped.
  localSource =
    name:
    let
      entry = hostEntry name;
    in
    optional (
      ownCluster != null && entry.network-cluster == ownCluster && entry.ip-local != null
    ) (access.hostCidr entry.ip-local);

  # Followers accept administration from leaders; leaders only from operators.
  trustedHosts = cfg.operatorHosts ++ optionals (cfg.tier == "follower") cfg.leaderHosts;

  hostList =
    description:
    mkOption {
      type = types.listOf types.str;
      default = [ ];
      inherit description;
    };
in
{
  options.luxnix.networkAccess = {
    tier = mkOption {
      type = types.enum access.tiers;
      default = "follower";
      description = ''
        Trust tier of this host. `follower` (EndoReg clients) accepts
        management from operators and leaders and serves only them; `leader`
        (servers and the central hub) accepts management from operators and
        serves the whole VPN. Roles set this with
        `lib.luxnix.networkAccess.mkTierDefault`, so leader roles win over
        follower roles and plain host or inventory assignments win over both.
      '';
    };

    operatorHosts = hostList ''
      Inventory host names of operator workstations trusted to administer
      this host. Resolved through `luxnix.generic-settings.network.hosts`.
    '';

    leaderHosts = hostList ''
      Inventory host names of leader hosts. Followers accept management from
      them; leaders ignore this list.
    '';

    vpnSubnet = mkOption {
      type = access.cidr;
      default = settings.vpnSubnet;
      defaultText = literalExpression "config.luxnix.generic-settings.vpnSubnet";
      description = "LuxNix VPN network served by leader hosts.";
    };

    extraManagementSources = mkOption {
      type = types.listOf access.cidr;
      default = [ (access.hostCidr settings.adminVpnIp) ];
      defaultText = literalExpression ''[ "''${config.luxnix.generic-settings.adminVpnIp}/32" ]'';
      description = "Additional management networks that are not inventory hosts.";
    };

    extraEarlyBootSources = mkOption {
      type = types.listOf access.cidr;
      default = [ ];
      description = ''
        Additional LAN networks allowed to reach early-boot unlock, for
        operator machines that are not in the inventory host map.
      '';
    };

    managementSources = mkOption {
      type = types.listOf access.cidr;
      default = unique (map vpnSource trustedHosts ++ cfg.extraManagementSources);
      defaultText = literalExpression "VPN /32 of operatorHosts (and leaderHosts on followers) ++ extraManagementSources";
      description = "Networks allowed to administer this host over the VPN.";
    };

    serviceSources = mkOption {
      type = types.listOf access.cidr;
      default = if cfg.tier == "leader" then [ cfg.vpnSubnet ] else cfg.managementSources;
      defaultText = literalExpression ''if tier == "leader" then [ vpnSubnet ] else managementSources'';
      description = "Networks allowed to use restricted browser and API services on this host.";
    };

    earlyBootSources = mkOption {
      type = types.listOf access.cidr;
      default = unique (concatMap localSource trustedHosts ++ cfg.extraEarlyBootSources);
      defaultText = literalExpression "LAN /32 of trusted hosts in this host's network-cluster ++ extraEarlyBootSources";
      description = ''
        LAN networks allowed to authenticate to early-boot unlock. Empty when
        no trusted host shares this host's network cluster; remote unlock then
        refuses to evaluate until a source is configured.
      '';
    };
  };
}
