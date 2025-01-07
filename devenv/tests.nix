# file: tests/my-services-test.nix
{ pkgs, ... }:

import <nixpkgs/nixos/tests/make-test.nix> {
  name = "my-services-test";

  # Define how many machines (nodes) you need in this test
  nodes = {
    myMachine = {
      # NixOS config for this VM, including enabling or configuring your service
      config = {
        services.openssh.enable = true;
        # services.myMainService = {
        #   enable = true;
        #   ...
        # };
      };
    };
  };

  # The test script that runs in the test driver after the VM is up
  testScript = ''
    # Wait for the services to come up
    $myMachine->waitForUnit("ssh.service");

    # If you want to ensure it’s “active”, do:
    $myMachine->systemctl("is-active ssh.service");

    # Similarly for your other “main services”. E.g.:
    # $myMachine->waitForUnit("myMainService.service");
    # $myMachine->systemctl("is-active myMainService.service");

    # You can also test connectivity, logs, etc.
  '';
}
