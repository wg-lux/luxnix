# Common Errors And Their Solutions

## Permission denied on nho run

'''
bash
nix-os-rebuild switch --flake .
'''

If this command returns a permission error,
run:

'''
bash
sudo nix-os-rebuild switch --flake .
'''

If nho returns an error with permission denied, you dont have admin privileges.

## Wrong Group In Ansible Inventory

The ansible inventory assigns groups to all users.

gpu-client is a study laptop
gpu_server is a server

If any part of the operating system doesnt work, please check if the current macchine is listed in the correct group at 

ansible/inventory/hosts.ini

For group definitions, check back with the definitions inside of ansible/inventory/group_vars

## My Laptop Doesnt Have Certain Apps Installed

Quick fix:

Install the missing apps using nix-shell. This is also great when testing out a package. Availability check at: https://search.nixos.org/packages
'''
bash
nix-shell -p firefox
'''

Thorough fix:

Check if the correct roles are added to your laptop or server. This is edited at:

/home/admin/luxnix/systems/x86_64-linux/gc-02/default.nix

Default role setup:

  roles = { 
    aglnet.client.enable = true;
    common.enable = true;
    desktop.enable = true;
    endoreg-client.enable = true;
    custom-packages.baseDevelopment = true;
    custom-packages.videoEditing = false;
    custom-packages.visuals = false;
    };

## I See The Error Message: "Directory Not Empty" on a Directory Not Tracked In The LuxNix Github Repository

Try out:
cleanup
nho

Then:
git fetch
git merge
rm -rf directory
nho

Then:
Raise issue on github

## No Home Defined
'''
bash
nhh 
error: [json.exception.parse_error.101] parse error at line 1, column 1: syntax error while parsing value - invalid literal; last read: 'h'
Error: 
   0: Failed to parse nix-eval output: 
'''

If the above error, or an error telling you that no home for this machine is defined arises, add your host machine to:

/home/admin/luxnix/systems/x86_64-linux

Remember to set correct roles and groups!





