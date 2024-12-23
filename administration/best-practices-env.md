# Best Practices for Working with `.env` Files in Development

This guide outlines best practices for managing `.env` files to securely and efficiently handle environment variables in our Python/Django projects using NixOS and development environments managed with flakes and devenv.

---

## **1. General Principles**
- **Single Source of Truth**: The `.env` file should contain all configuration values specific to your environment (e.g., secrets, API keys, database credentials).
- **Environment-Specific Configurations**: Use different `.env` files for development, staging, and production environments (e.g., `.env.dev`, `.env.prod`).
- **Never Commit Secrets**: Add `.env` files to `.gitignore` to prevent accidental commits to version control.
- **Validate Variables**: Use tools or libraries (like `django-environ`) to validate environment variable types and defaults.

---

## **2. File Structure**
Adopt a clean and consistent structure for `.env` files:

```plaintext
# General settings
DEBUG=True
SECRET_KEY=your_secret_key

# Database configuration
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432

# API keys
API_KEY=your_api_key

# Other configurations
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Best Practices for Structure:
- Use **uppercase** for variable names with underscores for separation.
- Group related variables (e.g., database settings together).
- Add comments for clarity when necessary.

---

## **3. Loading `.env` Files**
In Python/Django projects, use libraries like [`python-decouple`](https://github.com/henriquebastos/python-decouple) or [`django-environ`](https://django-environ.readthedocs.io/) to load `.env` files.

### Example with `django-environ`:
1. **Install the library**:
   ```bash
   pip install django-environ
   ```
2. **Setup in Django**:
   In your `settings.py`:
   ```python
   import environ

   # Initialize environment variables
   env = environ.Env(
       DEBUG=(bool, False),
   )

   # Load .env file
   environ.Env.read_env(env_file='.env')

   # Use variables
   DEBUG = env('DEBUG')
   SECRET_KEY = env('SECRET_KEY')
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',
           'NAME': env('DB_NAME'),
           'USER': env('DB_USER'),
           'PASSWORD': env('DB_PASSWORD'),
           'HOST': env('DB_HOST'),
           'PORT': env('DB_PORT'),
       }
   }
   ```

---

## **4. Nix Integration**
When using Nix with flakes or devenv, integrate `.env` management into your configuration:
1. **Import `.env` in Nix Shell**:
   Add the `.env` file contents into the shell environment:
   ```nix
   {
     devShells.default = pkgs.mkShell {
       buildInputs = [ pkgs.python3 pkgs.poetry ];
       shellHook = ''
         # Load .env variables
         if [ -f .env ]; then
           export $(grep -v '^#' .env | xargs)
         fi
       '';
     };
   }
   ```
   This ensures environment variables are available during shell sessions.

2. **Store Secrets Securely**:
   - Use NixOS modules for sensitive secrets (`programs.env.enable` or external secret managers like HashiCorp Vault).
   - Inject secrets into services using Nix modules to avoid hardcoding them in `.env`.

---

## **5. Managing Secrets**
1. **Use Templates for Team Collaboration**:
   - Share `.env.example` files to indicate required environment variables.
   - Example template:
     ```plaintext
     # Copy this file to .env and fill in the values
     DEBUG=
     SECRET_KEY=
     DB_NAME=
     DB_USER=
     DB_PASSWORD=
     ```

2. **Environment Variable Priority**:
   - When deploying or testing, prefer actual environment variables (`os.environ`) over `.env` files for production.

---

## **6. Deployment and Production**
1. **Separate Secrets Management**:
   Avoid relying on `.env` files directly in production. Use:
   - Docker secrets
   - Kubernetes ConfigMaps
   - NixOS `environment.etc` or `systemd` unit configuration:
    ```nix
    systemd.services.my-app = {
        environmentFile = "/path/to/.env";
    };
    ```

2. **Secure Access to `.env`**:
   - Ensure `.env` files are readable only by the application or administrators (`chmod 600 .env`).
   - Store production secrets in secure locations.

---

## **7. Debugging Tips**
1. **Check for Missing Variables**:
   Use `environ.Env`'s `env.bool`, `env.int`, or default values to handle missing variables gracefully.

2. **Log Loaded Variables**:
   Log which variables are loaded during debugging (but never log secrets).

3. **Audit `.env` Content**:
   Periodically review `.env` files to ensure no unused or deprecated variables remain.

---

## **8. Tools to Improve Workflow**
1. **Lint `.env` Files**:
   Use tools like [`dotenv-linter`](https://github.com/dotenv-linter/dotenv-linter) to check `.env` files for errors or inconsistencies.
   ```bash
   dotenv-linter .env
   ```

2. **Synchronize Across Environments**:
   Automate `.env` file generation using scripts or templates (e.g., `envsubst` in bash).

---

By adhering to these practices, we can ensure secure, maintainable, and effective handling of environment variables across all our Python/Django projects and Nix environments.