import re

def parse_shortcuts(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
        aliases = re.search(r'shellAliases\s*=\s*{([^}]*)}', content)
        if aliases:
            for line in aliases.group(1).split('\n'):
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    print(f"{key.strip():<15} {value.strip().replace(';','').replace('\"','')}")

parse_shortcuts('../../../home/cli/shells/zsh/default.nix')
