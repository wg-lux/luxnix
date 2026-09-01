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
            description = "Run a boot-time local encrypted-HLS backfill dispatcher after migrations, base data loading, and encrypted storage validation.";
          };
          extraArgs = mkOption {
            type = types.listOf types.str;
            default = [ ];
            example = literalExpression ''[ "--limit" "25" ]'';
            description = "Additional safe arguments passed to materialize_video_hls for the automatic backfill. By default the wrapper reconciles both raw and processed HLS artifacts; use --artifact-kind raw or --artifact-kind processed to limit a run. The wrapper rejects --force, --inline, and unsupported artifact kinds.";
          };
          timeoutStartSec = mkOption {
            type = types.str;
            default = "1h";
            description = "Maximum time allowed for dispatching automatic HLS backfill jobs.";
          };
        };
      };
      default = { };
      description = "Settings for the automatic local encrypted-HLS backfill dispatcher.";
    };
  };
}
