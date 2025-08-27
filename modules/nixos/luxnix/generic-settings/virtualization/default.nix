{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.luxnix.generic-settings.virtualization;
  hostname = config.networking.hostName;
  username = config.user.admin.name;
  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;

  # Helper function to convert bool to "1" or "0"
  boolToZeroOne = x: if x then "1" else "0";

  # Generate ACL string for libvirtd
  aclString = with lib.strings;
    concatMapStringsSep ",\n    "
    escapeNixString
    cfg.kvm.deviceACL;

  # Generate tmpfile entries for shared memory
  tmpfileEntry = name: f: "f /dev/shm/${name} ${f.mode} ${f.user} ${f.group} -";

in {
  options.luxnix.generic-settings.virtualization = {
    enable = mkEnableOption "Enable virtualization configuration";

    podman = {
      enable = mkBoolOpt true "Enable Podman containerization";
      dockerCompat = mkBoolOpt true "Enable Docker compatibility layer";
      socketEnable = mkBoolOpt true "Enable Docker socket compatibility";
      dnsEnabled = mkBoolOpt true "Enable DNS for default network";
      
      extraConfig = mkOption {
        type = types.attrs;
        default = {};
        description = ''
          Additional configuration options for Podman.
        '';
      };
    };

    kvm = {
      enable = mkBoolOpt false "Enable KVM virtualization";
      
      packages = mkOption {
        type = with types; listOf package;
        default = with pkgs; [
          libguestfs
          win-virtio
          win-spice
          virt-manager
          virt-viewer
        ];
        description = "Additional packages to install for KVM";
      };

      libvirtd = {
        allowedBridges = mkOption {
          type = with types; listOf str;
          default = ["nm-bridge" "virbr0"];
          description = "List of allowed bridge interfaces";
        };

        onBoot = mkOption {
          type = types.enum ["start" "ignore"];
          default = "ignore";
          description = "Action to take on boot for VMs";
        };

        onShutdown = mkOption {
          type = types.enum ["shutdown" "destroy"];
          default = "shutdown";
          description = "Action to take on shutdown for VMs";
        };

        clearEmulationCapabilities = mkBoolOpt true "Clear emulation capabilities";
      };

      deviceACL = mkOption {
        type = with types; listOf str;
        default = [
          "/dev/null" "/dev/full" "/dev/zero"
          "/dev/random" "/dev/urandom"
          "/dev/ptmx" "/dev/kvm"
        ];
        description = "Device access control list for libvirtd";
      };

      qemu = {
        swtpm = mkBoolOpt true "Enable software TPM support";
        ovmf = mkBoolOpt true "Enable OVMF/UEFI support";
        runAsRoot = mkBoolOpt false "Run QEMU as root user";
      };

      spiceUSBRedirection = mkBoolOpt true "Enable SPICE USB redirection";
      kvmgt = mkBoolOpt false "Enable Intel GVT-g support";
    };

    vfio = {
      enable = mkBoolOpt false "Enable VFIO GPU passthrough";

      IOMMUType = mkOption {
        type = types.enum ["intel" "amd"];
        default = "intel";
        description = "Type of IOMMU to use (intel or amd)";
      };

      devices = mkOption {
        type = with types; listOf (strMatching "[0-9a-f]{4}:[0-9a-f]{4}");
        default = [];
        example = ["10de:1b80" "10de:10f0"];
        description = "PCI device IDs to bind to vfio-pci driver";
      };

      disableEFIfb = mkBoolOpt false "Disable EFI framebuffer on boot";
      blacklistNvidia = mkBoolOpt false "Blacklist Nvidia GPU drivers";
      ignoreMSRs = mkBoolOpt false "Ignore model-specific registers";

      sharedMemoryFiles = mkOption {
        type = with types; attrsOf (submodule ({name, ...}: {
          options = {
            name = mkOption {
              visible = false;
              default = name;
              type = str;
            };
            user = mkOption {
              type = str;
              default = "root";
              description = "Owner of the shared memory file";
            };
            group = mkOption {
              type = str;
              default = "root"; 
              description = "Group owner of the shared memory file";
            };
            mode = mkOption {
              type = str;
              default = "0600";
              description = "File permissions for the shared memory file";
            };
          };
        }));
        default = {};
        description = "Shared memory files configuration for Looking Glass";
      };

      hugepages = {
        enable = mkBoolOpt false "Enable hugepages support";
        
        defaultPageSize = mkOption {
          type = types.strMatching "[0-9]*[kKmMgG]";
          default = "1M";
          description = "Default hugepage size (e.g., 1M, 2M, 1G)";
        };

        pageSize = mkOption {
          type = types.strMatching "[0-9]*[kKmMgG]";
          default = "1M";
          description = "Hugepage size to allocate at boot";
        };

        numPages = mkOption {
          type = types.ints.positive;
          default = 1024;
          description = "Number of hugepages to allocate at boot";
        };
      };

      lookingGlass = {
        enable = mkBoolOpt false "Enable Looking Glass support";
        
        sharedMemorySize = mkOption {
          type = types.str;
          default = "128M";
          description = "Size of shared memory for Looking Glass";
        };
      };
    };

    # Global virtualization settings
    supportedArchitectures = mkOption {
      type = with types; listOf str;
      default = [];
      example = ["aarch64-linux"];
      description = "Additional architectures to emulate";
    };

    userGroups = mkOption {
      type = with types; listOf str;
      default = ["libvirtd" "kvm"];
      description = "Groups to add admin user to for virtualization access";
    };
  };

  config = mkIf cfg.enable {
    # Enable core virtualization services based on configuration
    services.virtualisation.podman.enable = mkIf cfg.podman.enable true;
    services.virtualisation.kvm.enable = mkIf cfg.kvm.enable false;
    services.virtualisation.vfio.enable = mkIf cfg.vfio.enable false;

    # Configure virtualization services
    virtualisation = mkMerge [
      # Configure Podman
      (mkIf cfg.podman.enable {
        podman = {
          enable = true;
          dockerSocket.enable = cfg.podman.socketEnable;
          dockerCompat = cfg.podman.dockerCompat;
          defaultNetwork.settings = {
            dns_enabled = cfg.podman.dnsEnabled;
          } // cfg.podman.extraConfig;
        };
      })
      
      # Configure KVM
      (mkIf cfg.kvm.enable {
        kvmgt.enable = cfg.kvm.kvmgt;
        spiceUSBRedirection.enable = cfg.kvm.spiceUSBRedirection;

        libvirtd = {
          enable = true;
          allowedBridges = cfg.kvm.libvirtd.allowedBridges;
          onBoot = cfg.kvm.libvirtd.onBoot;
          onShutdown = cfg.kvm.libvirtd.onShutdown;
          
          qemu = {
            swtpm.enable = cfg.kvm.qemu.swtpm;
            ovmf = mkIf cfg.kvm.qemu.ovmf {
              enable = true;
              packages = [pkgs.OVMFFull.fd];
            };
            runAsRoot = cfg.kvm.qemu.runAsRoot;
            verbatimConfig = ''
              clear_emulation_capabilities = ${boolToZeroOne cfg.kvm.libvirtd.clearEmulationCapabilities}
              cgroup_device_acl = [
                ${aclString}
              ]
            '';
          };
        };
      })
    ];

    # Configure VFIO passthrough and additional architectures
    boot = mkMerge [
      # VFIO kernel configuration
      (mkIf cfg.vfio.enable {
        kernelParams = 
          (if cfg.vfio.IOMMUType == "intel" then [
            "intel_iommu=on"
            "intel_iommu=igfx_off"
          ] else [
            "amd_iommu=on"
          ])
          ++ (optional (builtins.length cfg.vfio.devices > 0)
            ("vfio-pci.ids=" + builtins.concatStringsSep "," cfg.vfio.devices))
          ++ (optional cfg.vfio.disableEFIfb "video=efifb:off")
          ++ (optionals cfg.vfio.ignoreMSRs [
            "kvm.ignore_msrs=1"
            "kvm.report_ignored_msrs=0"
          ])
          ++ (optionals cfg.vfio.hugepages.enable [
            "default_hugepagesz=${cfg.vfio.hugepages.defaultPageSize}"
            "hugepagesz=${cfg.vfio.hugepages.pageSize}"
            "hugepages=${toString cfg.vfio.hugepages.numPages}"
          ]);

        kernelModules = ["vfio_pci" "vfio_iommu_type1" "vfio"];
        initrd.kernelModules = ["vfio_pci" "vfio_iommu_type1" "vfio"];
        blacklistedKernelModules = optionals cfg.vfio.blacklistNvidia ["nvidia" "nouveau"];
      })

      # Additional architecture support
      {
        binfmt.emulatedSystems = cfg.supportedArchitectures;
      }
    ];

    # Install virtualization packages
    environment.systemPackages = with pkgs; 
      (optionals cfg.kvm.enable cfg.kvm.packages)
      ++ (optionals cfg.vfio.enable [
        virtiofsd
      ])
      ++ (optionals cfg.vfio.lookingGlass.enable [
        looking-glass-client
      ]);

    # Configure user groups for virtualization access
    users.users.${username} = {
      extraGroups = cfg.userGroups;
    };

    # Add qemu-libvirtd user if needed
    users.users."qemu-libvirtd" = mkIf (cfg.kvm.enable && !cfg.kvm.qemu.runAsRoot) {
      extraGroups = ["kvm" "input"];
      isSystemUser = true;
    };

    # VFIO-specific configurations
    services.udev.extraRules = mkIf cfg.vfio.enable ''
      SUBSYSTEM=="vfio", OWNER="root", GROUP="kvm"
    '';

    # Configure shared memory files for Looking Glass
    systemd.tmpfiles.rules = mkIf cfg.vfio.enable (
      (mapAttrsToList tmpfileEntry cfg.vfio.sharedMemoryFiles)
      ++ (optional cfg.vfio.lookingGlass.enable
        "f /dev/shm/looking-glass 0660 ${username} kvm -")
    );

    # Add admin user to sensitive service group for virtualization management
    users.groups.${sensitiveServiceGroupName}.members = 
      lib.mkIf (cfg.kvm.enable || cfg.vfio.enable) [ username ];

    # System-level assertions and warnings
    assertions = [
      {
        assertion = !cfg.vfio.enable || cfg.kvm.enable;
        message = "VFIO requires KVM to be enabled";
      }
      {
        assertion = !cfg.vfio.enable || (cfg.vfio.devices != []);
        message = "VFIO is enabled but no devices are specified";
      }
    ];

    warnings = 
      (optional (cfg.vfio.enable && cfg.vfio.blacklistNvidia) 
        "VFIO: Nvidia drivers are blacklisted - GPU passthrough will be used")
      ++ (optional (cfg.vfio.hugepages.enable && cfg.vfio.hugepages.numPages > 2048)
        "VFIO: Large number of hugepages allocated - ensure sufficient memory");

  };
}
