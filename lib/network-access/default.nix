{ lib, ... }:
# Pure helpers for client-network allowlists.
#
# Exposed through Snowfall as `lib.luxnix.networkAccess`, and importable by path
# (`import <repo>/lib/network-access { inherit lib; }`) for modules that are
# also evaluated outside the flake, such as standalone VM tests.
let
  inherit (lib)
    all
    elemAt
    filter
    fromHexString
    genList
    length
    mkOverride
    splitString
    toInt
    types
    ;

  # Broadest prefix accepted in an allowlist. Anything wider than a site
  # network (for example /0 or /8) is rejected rather than silently allowed.
  minPrefix = {
    ipv4 = 16;
    ipv6 = 48;
  };
  maxPrefix = {
    ipv4 = 32;
    ipv6 = 128;
  };

  pow2 = n: builtins.foldl' (acc: _: acc * 2) 1 (genList (i: i) n);

  # Decimal octets without leading zeros, so "010" cannot be read as octal.
  parseIpv4 =
    address:
    let
      parts = splitString "." address;
      valid = p: builtins.match "0|[1-9][0-9]{0,2}" p != null && toInt p <= 255;
    in
    if length parts == 4 && all valid parts then map toInt parts else null;

  # Returns eight 16-bit groups, or null. Embedded IPv4 suffixes and zone
  # identifiers are not accepted in allowlists.
  parseIpv6 =
    address:
    let
      halves = splitString "::" address;
      groupsOf = s: if s == "" then [ ] else splitString ":" s;
      validGroup = g: builtins.match "[0-9a-fA-F]{1,4}" g != null;
      toInts = map fromHexString;
    in
    if length halves == 1 then
      let
        groups = groupsOf address;
      in
      if length groups == 8 && all validGroup groups then toInts groups else null
    else if length halves == 2 then
      let
        head = groupsOf (elemAt halves 0);
        tail = groupsOf (elemAt halves 1);
        missing = 8 - length head - length tail;
      in
      if missing >= 1 && all validGroup (head ++ tail) then
        toInts head ++ genList (_: 0) missing ++ toInts tail
      else
        null
    else
      null;

  # True when every bit after `prefix` is zero; `width` is bits per word.
  hostBitsClear =
    width: words: prefix:
    let
      check =
        index: word:
        let
          start = index * width;
          kept = prefix - start;
        in
        if kept >= width then
          true
        else if kept <= 0 then
          word == 0
        else
          builtins.bitAnd word (pow2 (width - kept) - 1) == 0;
    in
    all (x: x) (lib.imap0 check words);

  parseCidr =
    value:
    let
      parts = splitString "/" value;
      address = elemAt parts 0;
      prefixText = elemAt parts 1;
      prefixValid = builtins.match "0|[1-9][0-9]{0,2}" prefixText != null;
      prefix = toInt prefixText;
      v4 = parseIpv4 address;
      v6 = parseIpv6 address;
    in
    if !(builtins.isString value) || length parts != 2 || !prefixValid then
      null
    else if v4 != null then
      {
        family = "ipv4";
        inherit address prefix;
        words = v4;
        width = 8;
      }
    else if v6 != null then
      {
        family = "ipv6";
        inherit address prefix;
        words = v6;
        width = 16;
      }
    else
      null;

  isAllowlistCidr =
    value:
    let
      parsed = parseCidr value;
    in
    parsed != null
    && parsed.prefix >= minPrefix.${parsed.family}
    && parsed.prefix <= maxPrefix.${parsed.family}
    && hostBitsClear parsed.width parsed.words parsed.prefix;

  # Single-address network for a bare IP; fails loudly on anything else.
  hostCidr =
    address:
    if parseIpv4 address != null then
      "${address}/32"
    else if parseIpv6 address != null then
      "${address}/128"
    else
      throw "networkAccess.hostCidr: '${toString address}' is not a numeric IPv4 or IPv6 address.";

  cidr = types.addCheck types.str isAllowlistCidr // {
    name = "allowlistCidr";
    description = "IPv4 (/16 to /32) or IPv6 (/48 to /128) network in CIDR notation with no host bits set";
  };

  # Leader roles must win over follower role defaults on hosts that carry
  # both (the central hub enables endoreg-client), while host and inventory
  # assignments at normal priority still override either.
  tierPriority = {
    follower = 1000;
    leader = 900;
  };
in
{
  networkAccess = {
    inherit
      cidr
      hostCidr
      isAllowlistCidr
      minPrefix
      parseCidr
      tierPriority
      ;
    tiers = builtins.attrNames tierPriority;
    mkTierDefault = tier: mkOverride tierPriority.${tier} tier;
    # Exposed for tests and assertion messages.
    invalid = filter (value: !(isAllowlistCidr value));
  };
}
