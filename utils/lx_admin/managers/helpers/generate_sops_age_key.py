import subprocess

def generate_sops_age_key():
    """
    Generates a sops-age key pair using the `age` CLI tool.

    Returns:
        tuple: (private_key, public_key)
    """
    result = subprocess.run(["age-keygen"], capture_output=True, text=True, check=True)
    private_key = result.stdout.strip()
    public_key = next(
        line for line in private_key.splitlines() if line.startswith("# public key: ")
    ).replace("# public key: ", "")
    return private_key, public_key
