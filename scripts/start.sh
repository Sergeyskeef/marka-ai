#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -f /etc/marka-guardian/config.json ] || docker inspect marka-bridge-1 >/dev/null 2>&1; then
  echo 'Protected installation detected. Use docs/SELF_UPGRADES.md; ordinary Compose replaces its protective mounts.' >&2
  exit 1
fi
echo 'Настройка отдельного Марка рядом с существующими сервисами.'
docker compose build
docker compose run --rm --no-deps mark setup
if ! docker compose run --rm --no-deps --entrypoint python mark -c 'import asyncio,sys; from pathlib import Path; from marka.provider import CodexProvider; state=asyncio.run(CodexProvider(home=Path("/state/codex")).status()); sys.exit(0 if state["authenticated"] else 1)'; then
  docker compose run --rm --no-deps mark login
fi
docker compose run --rm --no-deps mark doctor --live
if [ "${MARKA_SKIP_SEMANTIC:-0}" != "1" ]; then
  docker compose run --rm --no-deps mark models install
fi
docker compose up -d
docker compose ps
echo 'Марк запущен. Отправь своему боту /start с кодом, выданным setup.'
