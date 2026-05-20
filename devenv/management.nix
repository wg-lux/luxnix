# This file consolidates all management tasks, scripts, and container operations
# into a unified DevEnv-based approach using the centralized configuration.

{
  pkgs,
  lib,
  env,
  isDev ? false,
}:
let
  # Utility functions (legacy placeholders; kept for future use)
  containerName = mode: "${env.app.name}-${mode}-test";
  commonContainerArgs = mode: [ ];
  gpuArgs = ''
    : # GPU args placeholder
  '';
  customScripts = import ./scripts.nix {
    inherit
      pkgs
      lib
      env
      isDev
      ;
  };
  customProcesses = import ./processes.nix {
    inherit
      pkgs
      lib
      env
      isDev
      ;
  };
in
{
  # =============================================================================
  # UNIFIED TASK DEFINITIONS
  # =============================================================================

  tasks = {
    # Environment Management
    "env:setup" = {
      description = "Complete environment setup (replaces multiple scripts)";
      exec = ''
        echo "🔧 Setting up Luxnix DevEnv"


        # Step 1: Ensure directories
        export WORKING_DIR="''${WORKING_DIR:-$(pwd)}"

        # Step 2: CUDA environment setup (optional)
        devenv tasks run env:setup-cuda || true

        echo "✅ Environment setup complete!"
      '';
    };

    # CUDA setup (non-fatal)
    "env:setup-cuda" = {
      description = "Setup CUDA environment for PyTorch";
      exec = ''
        echo "🧪 Checking CUDA environment..."
        ${pkgs.uv}/bin/uv run python scripts/cuda/test_cuda_paths.py || true
        ${pkgs.uv}/bin/uv run python scripts/cuda/minimal_cuda_test.py || true
        echo "⚠️  CUDA setup finished (non-blocking)"
      '';
    };
  };

  # =============================================================================
  # UNIFIED SCRIPT DEFINITIONS
  # =============================================================================

  scripts = customScripts // {
    "manage".exec = ''
      subcmd="''${1:-help}"
      case "$subcmd" in
        "setup")
          echo "🔧 Setting up Lx Annotate..."
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
          devenv tasks run deploy:full
          ;;

        "help"|*)
          echo "Lx Management Commands"
          echo "============================"
          echo ""
          echo "Environment:"
          echo "  manage setup              - Complete environment setup"
          echo "  manage dev                - Switch to development mode"
          echo "  manage prod               - Switch to production mode"
          echo ""
          ;;
      esac
    '';

    # "run-server".exec =
    #   ''

    #     secretspec run --provider env uv run daphne -b "${env.DJANGO_HOST}" -p "${env.DJANGO_PORT}" lx_annotate.asgi:application    '';

    # "run-filewatcher".exec = ''
    #   echo "👀 Starting file watcher for auto-import..."
    #   secretspec run --provider env python manage.py run_filewatcher
    # '';

  };

  processes = customProcesses;
}
