# Ansible Setup Plan

## Prerequisites

1. Ensure SSH access to all machines.
2. Install Ansible on the control machine.

## Inventory Setup

1. Create an inventory file listing all the machines to be managed.

## Directory Structure

1. Create a directory structure for the Ansible project:

## Environment Details

- Managing ~30 NixOS x86_64 machines
- ed25519 certificate-based SSH access

## Roles & Services

- Configure Keycloak, Postgres, Postgres-Backup, Traefik, and custom microservices

## Secrets

- Use Ansible Vault for production environment secrets
