#!/usr/bin/env sh
set -eu

if command -v docker >/dev/null 2>&1; then
  docker --version
  exit 0
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to install Docker" >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 iproute2
sudo systemctl enable --now docker
TARGET_USER="${SUDO_USER:-$USER}"
sudo usermod -aG docker "$TARGET_USER" || true

echo "Docker installed. Log out and back in, or run: newgrp docker"
docker --version || sudo docker --version
