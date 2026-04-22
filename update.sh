#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

sudo docker compose down
git pull
sudo bash setup.sh
