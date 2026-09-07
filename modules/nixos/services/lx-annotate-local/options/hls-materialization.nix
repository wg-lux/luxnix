{ lib, ... }:
let
  inherit (lib) literalExpression mkOption types;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    hlsMaterialization = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Expose the manual local encrypted-HLS materialization systemd unit. The unit is not started by any target.";
          };
          extraArgs = mkOption {
            type = types.listOf types.str;
            default = [ ];
            example = literalExpression ''[ "--limit" "25" ]'';
            description = "Additional safe arguments passed to materialize_video_hls. By default the wrapper reconciles both raw and processed HLS artifacts; use --artifact-kind raw or --artifact-kind processed to limit a manual run. The wrapper rejects --force, --inline, and unsupported artifact kinds.";
          };
          timeoutStartSec = mkOption {
            type = types.str;
            default = "1h";
            description = "Maximum time allowed for dispatching HLS materialization jobs.";
          };
        };
      };
      default = { };
      description = "Settings for the manual local raw or processed encrypted-HLS materialization unit.";
    };
  };
}
