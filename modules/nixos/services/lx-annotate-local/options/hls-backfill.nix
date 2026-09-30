{ lib, ... }:
let
  inherit (lib) literalExpression mkOption types;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    hlsBackfill = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Mandatory compatibility option. It defaults to true and must remain true so every enabled host automatically replaces legacy raw and processed HLS after migrations, base data loading, and encrypted storage validation.";
          };
          extraArgs = mkOption {
            type = types.listOf types.str;
            default = [ ];
            example = literalExpression "[ ]";
            description = "Reserved compatibility field. It must remain empty so the automatic production backfill reconciles the entire raw and processed HLS corpus without per-machine opt-in or selection. Use the separate manual materialization unit for scoped repair runs.";
          };
          timeoutStartSec = mkOption {
            type = types.str;
            default = "1h";
            description = "Maximum time allowed for dispatching automatic HLS backfill jobs.";
          };
        };
      };
      default = { };
      description = "Settings for the mandatory automatic full-corpus local encrypted-HLS replacement dispatcher.";
    };
  };
}
