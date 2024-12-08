{
  config,
  pkgs,
  lib,
  ...
}:
with lib; 
with lib.luxnix;
let
  cfg = config.desktops.plasma;
  # https://nix-community.github.io/plasma-manager/
in {
  # imports = lib.snowfall.fs.get-non-default-nix-files ./.;

  options.desktops.plasma = {
    enable = mkBoolOpt true "enable plasma DE";
  };

  config = mkIf cfg.enable {
    programs.plasma = {
      enable = true;

      #
      # Some high-level settings:
      #
      workspace = {
      clickItemTo = "select";
      lookAndFeel = "org.kde.breezedark.desktop";
      cursor.theme = "Bibata-Modern-Ice";
      iconTheme = "Papirus-Dark";
      #TODO customize
      wallpaper = "${pkgs.kdePackages.plasma-workspace-wallpapers}/share/wallpapers/Patak/contents/images/1080x1920.png";
    };


      hotkeys.commands."launch-konsole" = {
        name = "Launch Konsole";
        key = "Meta+Alt+K";
        command = "konsole";
      };

      fonts = {
        general = {
          family = "JetBrains Mono";
          pointSize = 12;
        };
      };

      desktop.widgets = [
        # {
          # plasmusicToolbar = {
          #   position = {
          #     horizontal = 51;
          #     vertical = 100;
          #   };
          #   size = {
          #     width = 250;
          #     height = 250;
          #   };
          # };
        # }
      ];

      panels = [
        # Windows-like panel at the bottom
        {
          location = "bottom";
          widgets = [           
            {
              name = "org.kde.plasma.kickoff";
              config = {
                General = {
                  icon = "nix-snowflake-white";
                  alphaSort = true;
                };
              };
            }
{
            iconTasks = {
                launchers = [
                  # "applications:org.kde.dolphin.desktop"
                  "applications:org.kde.konsole.desktop"
                ];
              };
            }

            # "org.kde.plasma.marginsseparator"
            {
              digitalClock = {
                calendar.firstDayOfWeek = "monday";
                time.format = "24h";
              };
            }
            {
              systemTray.items = {
                # We explicitly show 
                shown = [
                  "org.kde.plasma.battery"
                  "org.kde.plasma.networkmanagement"
                ];
                # And explicitly hide
                hidden = [
                  "org.kde.plasma.volume"
                  "org.kde.plasma.bluetooth"
                ];
              };
            }
          ];
          # hiding = "autohide";
        }
        # Application name, Global menu and Song information and playback controls at the top
        {
          location = "top";
          height = 26;
          widgets = [
            {
              applicationTitleBar = {
                behavior = {
                  activeTaskSource = "activeTask";
                };
                layout = {
                  elements = [ "windowTitle" ];
                  horizontalAlignment = "left";
                  showDisabledElements = "deactivated";
                  verticalAlignment = "center";
                };
                overrideForMaximized.enable = false;
                titleReplacements = [
                  {
                    type = "regexp";
                    originalTitle = "^Brave Web Browser$";
                    newTitle = "Brave";
                  }
                  {
                    type = "regexp";
                    originalTitle = ''\\bDolphin\\b'';
                    newTitle = "File manager";
                  }
                ];
                windowTitle = {
                  font = {
                    bold = false;
                    fit = "fixedSize";
                    size = 12;
                  };
                  hideEmptyTitle = true;
                  margins = {
                    bottom = 0;
                    left = 10;
                    right = 5;
                    top = 0;
                  };
                  source = "appName";
                };
              };
            }
            "org.kde.plasma.appmenu"
            "org.kde.plasma.panelspacer"
            # {
            #   plasmusicToolbar = {
            #     panelIcon = {
            #       albumCover = {
            #         useAsIcon = false;
            #         radius = 8;
            #       };
            #       icon = "view-media-track";
            #     };
            #     playbackSource = "auto";
            #     musicControls.showPlaybackControls = true;
            #     songText = {
            #       displayInSeparateLines = true;
            #       maximumWidth = 640;
            #       scrolling = {
            #         behavior = "alwaysScroll";
            #         speed = 3;
            #       };
            #     };
            #   };
            # }
          ];
        }
      ];

      window-rules = [
        {
          description = "Dolphin";
          match = {
            window-class = {
              value = "dolphin";
              type = "substring";
            };
            window-types = [ "normal" ];
          };
          apply = {
            noborder = {
              value = true;
              apply = "force";
            };
            # `apply` defaults to "apply-initially"
            maximizehoriz = true;
            maximizevert = true;
          };
        }
      ];

      powerdevil = {
        AC = {
          powerButtonAction = "lockScreen";
          autoSuspend = {
            action = "nothing"; # null or one of “hibernate”, “nothing”, “shutDown”, “sleep”
            # idleTimeout = 1000; # The duration (in seconds), when on AC, the computer must be idle for until the auto-suspend action is executed
          };
          dimDisplay = {
            enable = true;
            idleTimeout = (15 * 60);
          };
          turnOffDisplay = {
            idleTimeout = (20 * 60);
            idleTimeoutWhenLocked = "immediately";
          };
          displayBrightness = 100;
          powerProfile = "balanced";
        };
        battery = {
          powerButtonAction = "sleep";
          whenSleepingEnter = "standbyThenHibernate";
        };
        lowBattery = {
          whenLaptopLidClosed = "hibernate";
        };
      };

      kwin = {
        edgeBarrier = 0;        # Disables the edge-barriers introduced in plasma 6.1
        cornerBarrier = false;  # When enabled, prevents the cursor from crossing at screen-corners.

        scripts.polonium.enable = true;
        borderlessMaximizedWindows = true;

        nightLight = {
          mode = "location";
          # Set Würzburg, Germany
          location.longitude = "9.92937";
          location.latitude = "49.79441";
          temperature = {
            night = 3750;
          };
        };

      };

      kscreenlocker = {
        appearance = {
          alwaysShowClock = true;
          wallpaper = "${pkgs.kdePackages.plasma-workspace-wallpapers}/share/wallpapers/Kay/contents/images/1080x1920.png";

        };
        lockOnResume = true;
        autoLock = true;
        timeout = 10;
        lockOnStartup = true;
        passwordRequired = true;
        passwordRequiredDelay = 10; # The time it takes in seconds for the password to be required after the screen is locked.

        
      };

      #
      # Some mid-level settings:
      #
      shortcuts = {
        ksmserver = {
          "Lock Session" = [
            "Screensaver"
            "Meta+Ctrl+Alt+L"
          ];
        };

        kwin = {
          "Expose" = "Meta+,";
          "Switch Window Down" = "Meta+J";
          "Switch Window Left" = "Meta+H";
          "Switch Window Right" = "Meta+L";
          "Switch Window Up" = "Meta+K";
        };
      };

      #
      # Some low-level settings:
      #
      configFile = {
        baloofilerc."Basic Settings"."Indexing-Enabled" = false;
        kwinrc."org.kde.kdecoration2".ButtonsOnLeft = "SF";
        kwinrc.Desktops.Number = {
          value = 8;
          # Forces kde to not change this value (even through the settings app).
          immutable = true;
        };
        # kscreenlockerrc = {
        #   Greeter.WallpaperPlugin = "org.kde.potd";
        #   # To use nested groups use / as a separator. In the below example,
        #   # Provider will be added to [Greeter][Wallpaper][org.kde.potd][General].
        #   "Greeter/Wallpaper/org.kde.potd/General".Provider = "bing";
        # };
    };
    };
   
  };
}
