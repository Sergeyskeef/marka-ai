#!/usr/bin/env bash
set -e

BACKUP_DIR="$HOME/backups"
KEEP_DAYS=7
TG_TOKEN="${BOT_TOKEN}"         # уже есть в .env
TG_CHAT_ID="${ADMIN_CHAT}"      # добавьте в .env id своего чата

pause()   { docker compose pause   weaviate; }
unpause() { docker compose unpause weaviate; }

echo "⏳  Pausing weaviate…"
pause

FILE="$BACKUP_DIR/weaviate_$(date +%F_%H-%M).tgz"
echo "📦  Creating archive $FILE …"
tar -czf "$FILE" -C "$(docker volume inspect weaviate-data -f '{{.Mountpoint}}')" .

echo "▶️  Unpausing weaviate…"
unpause
echo "✅  Backup done."

# --- cleanup ---
find "$BACKUP_DIR" -name 'weaviate_*.tgz' -mtime +$KEEP_DAYS -delete

# --- telegram notify (опционально) ---
if [[ -n "$TG_TOKEN" && -n "$TG_CHAT_ID" ]]; then
  MSG="✅ Weaviate backup created: $(basename "$FILE")"
  curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
       -d chat_id="$TG_CHAT_ID" -d text="$MSG" >/dev/null
fi

