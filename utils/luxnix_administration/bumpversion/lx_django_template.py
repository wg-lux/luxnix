import subprocess
import json
from pathlib import Path

# Paths to files
repo_url = "https://github.com/wg-lux/lx-django-template"
default_nix_path = Path("../modules/home/luxnix/django-demo-app/default.nix")
json_file_path = default_nix_path.parent / "repo_info.json"
# json_file_path = json_file_path.resolve()

# Run nix-prefetch-git and fetch the repo metadata
def fetch_repo_info(repo_url):
    try:
        result = subprocess.run(
            ["nix-prefetch-git", repo_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        repo_info = json.loads(result.stdout)
        return repo_info
    except subprocess.CalledProcessError as e:
        print(f"Error running nix-prefetch-git: {e.stderr}")
        return None

def write_to_json_file(json_file_path, repo_info):
    # # Ensure the directory exists
    # json_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write the JSON file
    with open(json_file_path, "w") as file:
        json.dump(repo_info, file, indent=4)
    print(f"Metadata written to {json_file_path}.")


# Compare existing and new JSON data
def compare_json(json_file_path, new_data):
    if json_file_path.exists():
        with open(json_file_path, "r") as file:
            current_data = json.load(file)
        
        # Compare revisions and hashes
        current_rev = current_data.get("rev")
        current_sha256 = current_data.get("sha256")
        new_rev = new_data.get("rev")
        new_sha256 = new_data.get("sha256")

        if current_rev == new_rev and current_sha256 == new_sha256:
            print("The version is still the same.")
            print(f"Current version: rev={current_rev}, sha256={current_sha256}")
            return False  # No update needed
        else:
            print("The version has been updated.")
            print(f"Previous version: rev={current_rev}, sha256={current_sha256}")
            print(f"New version: rev={new_rev}, sha256={new_sha256}")
            return True  # Update needed
    else:
        print("No existing JSON file found. Creating a new one.")
        return True  # Update needed

# Main function
def main():
    repo_info = fetch_repo_info(repo_url)
    if not repo_info:
        return

    # Extract rev and sha256 from fetched data
    rev = repo_info.get("rev")
    sha256 = repo_info.get("sha256")
    if not rev or not sha256:
        print("Failed to fetch rev or sha256.")
        return

    # Check if update is needed
    if compare_json(json_file_path, repo_info):
        write_to_json_file(json_file_path, repo_info)

if __name__ == "__main__":
    main()
