# Central composition point for Devenv tasks, scripts, and processes.

{ pkgs, ... }:
let
  customScripts = import ./scripts.nix { inherit pkgs; };
  customProcesses = import ./processes.nix { };
  customTasks = import ./tasks.nix { inherit pkgs; };
in
{
  # Environment setup tasks supplement the repository tasks from tasks.nix.
  tasks = customTasks // {
    "env:setup" = {
      description = "Prepare the development shell and probe optional CUDA support";
      exec = ''
        echo "🔧 Setting up the LuxNix development environment"

        export WORKING_DIR="''${WORKING_DIR:-$(pwd)}"
        devenv tasks run env:setup-cuda || true

        echo "✅ Environment setup complete!"
      '';
    };

    "env:setup-cuda" = {
      description = "Probe optional CUDA support without blocking shell setup";
      exec = ''
        echo "🧪 Checking CUDA environment..."
        ${pkgs.uv}/bin/uv run python scripts/cuda/test_cuda_paths.py || true
        ${pkgs.uv}/bin/uv run python scripts/cuda/minimal_cuda_test.py || true
        echo "⚠️  CUDA setup finished (non-blocking)"
      '';
    };
  };

  # Interactive convenience wrapper for local environment management.
  scripts = customScripts // {
    manage.package = pkgs.zsh;
    manage.exec = ''
      subcmd="''${1:-help}"
      case "$subcmd" in
        "setup")
          echo "🔧 Setting up LuxNix..."
          devenv tasks run env:setup
          ;;
        "dev")
          echo "development" > .mode
          echo "🔄 Switched to development mode"
          devenv tasks run env:setup
          ;;
        "prod") 
          echo "production" > .mode
          echo "🔄 Switched to production mode"
          devenv tasks run env:setup
          ;;
        "deploy")
          echo "No generic deployment task is defined because deployment requires an explicit host and target." >&2
          echo "See docs/deployment-guide.md or the deploy-new-host workflow in luxnix.yml." >&2
          exit 2
          ;;
        "help")
          echo "LuxNix management commands"
          echo "==========================="
          echo ""
          echo "Environment:"
          echo "  manage setup   Prepare the development environment"
          echo "  manage dev     Switch to development mode"
          echo "  manage prod    Switch to production mode"
          echo "  manage deploy  Show the canonical deployment guidance"
          echo ""
          echo "All wrappers, tasks, usage, and risk labels:"
          echo "  devenv/commands.yml"
          echo "Machine-readable project workflows:"
          echo "  luxnix.yml"
          echo ""
          ;;
        *)
          echo "Unknown manage command: $subcmd" >&2
          echo "Run 'manage help' to list supported commands." >&2
          exit 2
          ;;
      esac
    '';
  };

  processes = customProcesses;
}
