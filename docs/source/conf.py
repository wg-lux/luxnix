import os
import sys
sys.path.insert(0, os.path.abspath('../..'))  # Make your project root visible to Sphinx

# -- Project information -----------------------------------------------------
project = 'LUXNIX'
copyright = '2025, AG-LUX'
author = 'AG-LUX'
release = '0.1.0'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.viewcode',
    'sphinx.ext.todo',
    'sphinx.ext.autosectionlabel',
    'sphinx.ext.githubpages',
    'sphinx.ext.intersphinx',  # optional, links to external docs
]

# Syntax highlighting language
highlight_language = 'nix'

# Paths and patterns
templates_path = ['_templates']
exclude_patterns = []

# Intersphinx mappings (optional, remove if not needed)
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
