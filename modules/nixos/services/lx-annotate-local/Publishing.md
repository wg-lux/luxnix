# Publishing lx-annotate

When debugging lx-annotate workflows, the issue could lie in various parts of the dependencies.
Therefore, it might be necessary to publish especially lx-anonymizer and endoreg-db before publishing a new version of lx-annotate with a fix.

## lx-data-models

If a issue arises in one of the contracts its probably from lx-data-models. Also if something goes wrong in the api related to the reporting functionality of lx-annotate look here. https://github.com/wg-lux/lx-data-models .

```
bash
git clone https://github.com/wg-lux/lx-data-models
pre-commit install
git commit -m ""
git push origin branch
python -m build
python -m twine upload 
```

## lx-anonymizer

When a issue happens in the FrameCleaner or ReportReader cli, be sure to check the code of https://github.com/wg-lux/lx-anonymizer for the error. Clone it, edit it, change the version.

```
bash
git clone https://github.com/wg-lux/lx-anonymizer
uv sync --extra dev
pre-commit install
git commit -m ""
git push origin branch
make package
python -m twine upload 
```

Caution: If you changed lx-dtypes/lx-data-models you need to run:

```
bash
uv add lx-dtypes=="your-version"
```

## endoreg_db

When a issue happens in the persistance layer or the annotation api, be sure to check the code of https://github.com/wg-lux/endoreg-db for the error. Clone it, edit it, change the version, publish.

```
bash
git clone https://github.com/wg-lux/endoreg-db
uv sync --extra dev
pre-commit install
git commit -m ""
git push origin branch
make package
python -m twine upload 
```

Caution: If you changed lx-dtypes/lx-data-models or lx-anonymizer you need to run:

```
bash
uv remove lx-anonymizer && uv add lx-dtypes=="your-version" && uv add lx-anonymizer=="your-version"
```

## lx-annotate

Frontend, API orchestration and security settings are mostly in https://github.com/wg-lux/lx-annotate. If you edited the dependencies of lx-annotate package, proceed to install the changes and then publish lx-annotate.
```
bash
git clone https://github.com/wg-lux/lx-annotate
uv sync --extra dev
pre-commit install
git commit -m ""
git push origin branch
make package
python -m twine upload 
```

Caution: If you changed lx-dtypes/lx-data-models or lx-anonymizer or endoreg-db you need to run:

```
bash
uv remove endoreg-db && uv remove lx-anonymizer && uv add lx-dtypes=="your-version" && uv add lx-anonymizer=="your-version" && uv add endoreg-db=="your-version"
```


## Luxnix

LuxNix uses a wheel-based deployment of lx-annotate. This is managed in this
folder; the path option lives in `options.nix`. To update it, open the
[lx-annotate release history](https://pypi.org/project/lx-annotate/#history) and
copy the link for the latest `.whl` file.
```
bash
nix hash convert --hash-algo sha256 --to sri \
  $(nix-prefetch-url https://files.pythonhosted.org/packages/ad/36/219898d35d88162336bd0d9e2afbc0d40b606ade19c1c18ccc9ed43f3552/lx_annotate-0.8.3-py3-none-any.whl)

# OUTPUT OF SHA HASH WILL BE HERE
```

Update the wheel-path option in `options.nix`.
```
nix
            default = pkgs.fetchurl {
              url = "https://files.pythonhosted.org/packages/ad/36/219898d35d88162336bd0d9e2afbc0d40b606ade19c1c18ccc9ed43f3552/lx_annotate-0.8.3-py3-none-any.whl";
              hash = "sha256-cwmCkKKyq714ITHazl+ZSPDXqhL+OBxSKSPPRBLlmnw=";
            };
```


Then, proceed to rebuild the gc-clients luxnix system to see the changes in effect.
