from pathlib import Path
from lx_administration.autoconf.main import pipe as pipe

# Make sure Host Facts are available at ansible/cmdb
# run scripts/ansible-cmdb.sh (if required)

# Make sure Inventory is available at ansible/inventory


if __name__ == "__main__":
    ansible_root = Path("./ansible")
    autoconf_out = Path("./autoconf")
    # nix_out = Path("./autoconf")
    nix_out = Path(".")

    pipe(ansible_root, autoconf_out, nix_out)
