from pathlib import Path
from lx_administration.autoconf.main import pipe as pipe

if __name__ == "__main__":
    ansible_root = Path("./ansible")
    autoconf_out = Path("./autoconf")

    pipe(ansible_root, autoconf_out)
