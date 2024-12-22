import json
from pathlib import Path

def load_secrets(secrets_file):
    secrets_path = Path(secrets_file)
    with open(secrets_path) as f:
        secrets = json.load(f)
    return secrets
