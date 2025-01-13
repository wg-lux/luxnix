{config, pkgs, ...}@inputs: {
  
  roles = {
    # base-server.enable= true; 
    aglnet = {
      host.enable = false;
      client.enable = true;
    }; 
    gpu-client-dev.enable = true;   # Enables common, desktop(with plasma) and laptop-gpu roles                                # Also enables aglnet.client.enable = true;
    postgres.main.enable = false;
    ssh-access.dev-01.enable = true;
  };
}