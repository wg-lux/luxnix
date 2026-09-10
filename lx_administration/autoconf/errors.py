"""Public errors raised by the Autoconf generation pipeline."""

import yaml


class AutoconfConfigError(ValueError):
    """Raised when the central Autoconf configuration is invalid."""


class AutoconfPipelineError(RuntimeError):
    """Raised when valid configuration cannot produce a complete output set."""


class AutoconfSourceError(AutoconfPipelineError, ValueError):
    """Raised when configured input files conflict or have an invalid shape."""


class AutoconfSourceNotFoundError(AutoconfSourceError, FileNotFoundError):
    """Raised when a configured Autoconf input path does not exist."""


class AutoconfYamlError(AutoconfSourceError, yaml.YAMLError):
    """Raised when a configured YAML source cannot be parsed safely."""


class AnsibleFactFormatError(AutoconfPipelineError, ValueError):
    """Raised when a saved Ansible setup response has an unsafe shape."""
