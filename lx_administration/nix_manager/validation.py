from .utils import parse_nix_file, find_duplicates, remove_duplicates


def validate_default_nix_file(filepath):
    content = parse_nix_file(filepath)
    for section in ["user", "roles", "services"]:
        content = remove_duplicates(content, section)
    with open(filepath, "w") as file:
        file.write(content)


# Example usage
# validate_default_nix_file('/home/admin/dev/luxnix/systems/x86_64-linux/s-02/default.nix')
