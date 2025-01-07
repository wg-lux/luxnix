# Setup Pre Commit Hook
To set up auto-formatting for your Python and Nix files, we can use black for Python and nixpkgs-fmt for Nix files. Here are the steps to proceed:

Install the necessary tools:

Ensure black and nixpkgs-fmt are included in your development environment.
Configure pre-commit hooks:

Use pre-commit to run black and nixpkgs-fmt automatically before each commit.
Update your CI configuration:

Ensure your CI pipeline checks the formatting.
Step 1: Install the necessary tools
Ensure black and nixpkgs-fmt are included in your devenv.nix or devenv.nix:

```nix
packages = with pkgs; [
  black
  nixpkgs-fmt
  # other packages
];
```

Step 2: Configure pre-commit hooks
Create a .pre-commit-config.yaml file in the root of your repository:

```yml
repos:
  - repo: https://github.com/psf/black
    rev: 23.1.0  # Use the latest version
    hooks:
      - id: black
  - repo: https://github.com/nix-community/nixpkgs-fmt
    rev: v1.2.0  # Use the latest version
    hooks:
      - id: nixpkgs-fmt
        files: \.nix$
```

Install pre-commit
```shell
uv add pre-commit
pre-commit install
```
-> `pre-commit installed at .git/hooks/pre-commit`

Step 3: 
Update ci.yml workflow
```yml
name: CI
on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install pre-commit
          pre-commit install
          pip install .
      - name: Run pre-commit hooks
        run: pre-commit run --all-files
      - name: Run tests
        run: python -m unittest discover
```

