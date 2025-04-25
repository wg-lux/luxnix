Nix Scripts Documentation
=========================

This section documents all available Nix-based CLI commands.


Hello Command
-------------

**Sets up** a CLI tool called ``hello`` using ``zsh``.

**Purpose:**  
Runs a Python script named ``hello.py`` using ``uv``, a modern Python runner for faster dependency management and execution.

**Equivalent shell command:**

.. code-block:: bash

   uv run python hello.py

**Nix configuration:**

.. code-block:: nix

   hello.package = pkgs.zsh;
   hello.exec = "${pkgs.uv}/bin/uv run python hello.py";


BNSC Command
------------

**Sets up** a CLI tool for running the autoconf pipeline.

**Purpose:**  
Executes ``scripts/autoconf-pipeline.py`` using ``uv``.

**Equivalent shell command:**

.. code-block:: bash

   uv run python scripts/autoconf-pipeline.py

**Nix configuration:**

.. code-block:: nix

   bnsc.package = pkgs.zsh;
   bnsc.exec = "${pkgs.uv}/bin/uv run python scripts/autoconf-pipeline.py";


BLXV Command
------------

**Sets up** a CLI tool for bootstrapping the Lux Vault.

**Purpose:**  
Runs the ``bootstrap-lx-vault.py`` script.

**Equivalent shell command:**

.. code-block:: bash

   uv run python scripts/bootstrap-lx-vault.py

**Nix configuration:**

.. code-block:: nix

   blxv.package = pkgs.zsh;
   blxv.exec = "${pkgs.uv}/bin/uv run python scripts/bootstrap-lx-vault.py";


Run Ansible
-----------

**Sets up** a CLI wrapper for Ansible playbooks.

**Purpose:**  
Executes the ``ansible/site.yml`` playbook via ``uv``.

**Equivalent shell command:**

.. code-block:: bash

   uv run ansible-playbook ansible/site.yml

**Nix configuration:**

.. code-block:: nix

   run-ansible.package = pkgs.zsh;
   run-ansible.exec = "${pkgs.uv}/bin/uv run ansible-playbook ansible/site.yml";


SSH All
-------

**Sets up** a script to launch all Luxnix SSH sessions in tmux.

**Purpose:**  
Launches the ``all-luxnix-dir.sh`` script.

**Equivalent shell command:**

.. code-block:: bash

   ./tmux/all-luxnix-dir.sh

**Nix configuration:**

.. code-block:: nix

   ssh-all.package = pkgs.zsh;
   ssh-all.exec = "./tmux/all-luxnix-dir.sh";


Init Server SSH
---------------

**Sets up** SSH server init automation using tmux.

**Purpose:**  
Starts SSH server setup session.

**Equivalent shell command:**

.. code-block:: bash

   ./tmux/init-server-ssh.sh

**Nix configuration:**

.. code-block:: nix

   init-server-ssh.package = pkgs.zsh;
   init-server-ssh.exec = "./tmux/init-server-ssh.sh";


Kill Server SSH
---------------

**Sets up** a kill-switch for SSH tmux session.

**Purpose:**  
Stops the `ssh-servers` tmux session.

**Equivalent shell command:**

.. code-block:: bash

   tmux kill-session -t ssh-servers

**Nix configuration:**

.. code-block:: nix

   kill-server-ssh.package = pkgs.zsh;
   kill-server-ssh.exec = "tmux kill-session -t ssh-servers";


Connect Server SSH
------------------

**Sets up** CLI to attach to existing SSH server tmux session.

**Purpose:**  
Attaches to the running `ssh-servers` tmux session.

**Equivalent shell command:**

.. code-block:: bash

   tmux attach-session -t ssh-servers

**Nix configuration:**

.. code-block:: nix

   conn-server-ssh.package = pkgs.zsh;
   conn-server-ssh.exec = "tmux attach-session -t ssh-servers";


Sync Secrets
------------

**Sets up** a secret sync automation script.

**Purpose:**  
CLI wrapper for syncing secrets (details not shown in original).

**Nix configuration:**

.. code-block:: nix

   sync-secrets.package = pkgs.zsh;


Create SSH Keypair
------------------

**Sets up** CLI to create SSH keypair.

**Purpose:**  
Runs script to generate `ed25519` SSH key.


**Nix configuration:**

.. code-block:: nix

   create-ed25519-keypair.package = pkgs.zsh;


Autoconf (AC)
-------------

**Sets up** a CLI command for autoconf state.

**Purpose:**  
Triggers a custom task via `devenv`.

**Equivalent shell command:**

.. code-block:: bash

   devenv tasks run autoconf:finished

**Nix configuration:**

.. code-block:: nix

   ac.package = pkgs.zsh;
   ac.exec = "devenv tasks run autoconf:finished";


Unit Test (UTest)
-----------------

**Sets up** CLI to run Python unit tests via `uv`.

**Purpose:**  
Runs `unittest` using `uv`.

**Equivalent shell command:**

.. code-block:: bash

   uv run python -m unittest

**Nix configuration:**

.. code-block:: nix

   utest.package = pkgs.zsh;
   utest.exec = "${pkgs.uv}/bin/uv run python -m unittest";


Initialize Luxnix Repo
----------------------

**Sets up** repo initialization command.

**Purpose:**  
Runs a setup that allows direnv and marks the repo as initialized.

**Equivalent shell command:**

.. code-block:: bash

   direnv allow
   touch .repo_initialized

**Nix configuration:**

.. code-block:: nix

   initialize-luxnix-repo.exec = ''
     direnv allow
     touch .repo_initialized
   '';


Ensure Ansible Config
----------------------

**Sets up** a fallback for missing `ansible.cfg`.

**Purpose:**  
Copies template ansible config if not present.

**Equivalent shell command:**

.. code-block:: bash

   cp -n ./conf/TEMPLATE_ansible.cfg ./conf/ansible.cfg

**Nix configuration:**

.. code-block:: nix

   ensure-ansible-config.package = pkgs.zsh;
   ensure-ansible-config.exec = "cp -n ./conf/TEMPLATE_ansible.cfg ./conf/ansible.cfg";
