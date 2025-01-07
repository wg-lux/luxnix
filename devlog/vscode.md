# Set up Autoformatting
{

    "editor.formatOnSave": true,
    "[python]": {
      "editor.defaultFormatter": "ms-python.python"
    },
    "[nix]": {
      "editor.defaultFormatter": "B4dM4n.nixpkgs-fmt"
    },
    "[json]": {
        "editor.defaultFormatter": "esbenp.prettier-vscode"
    },
    "[javascript]": {
        "editor.defaultFormatter": "esbenp.prettier-vscode"
    },
    "editor.formatOnPaste": true,
    "editor.formatOnType": true,
    "python.formatting.provider": "black",
    "python.formatting.blackArgs": [
      "--line-length",
      "88"
    ],
    "favorites.resources": [
        {
            "filePath": "lx-administration/pyproject.toml",
            "group": "Default"
        },
        {
            "filePath": "lx-administration/devenv.nix",
            "group": "lx-administration"
        },
        {
            "filePath": "lx-administration/pyproject.toml",
            "group": "lx-administration"
        }
    ],
    "favorites.groups": [
        "Default",
        "lx-administration"
    ],
    "favorites.currentGroup": "lx-administration",
    "python.testing.unittestArgs": [
        "-v",
        "-s",
        "./lx-administration",
        "-p",
        "test_*.py"
    ],
    "python.testing.pytestEnabled": false,
    "python.testing.unittestEnabled": true
}
