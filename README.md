# Проект «Марк» — минимальная, но расширяемая сборка (апрель 2025)

## Быстрый старт

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

unzip marka_full_bundle.zip -d marka
cd marka/langchain_api
cp .env.example .env         # впиши OPENAI_API_KEY, BOT_TOKEN, прокси
docker compose up -d --build

curl http://localhost:8000/ping      # {"status":"ok"}
/start в Telegram → «Привет! Я — Марк (MVP).»
```

## Наращивание функций

* `make enable-rag` — RAG v2 (история+опыт)
* `make enable-sandbox` — Dev sandbox
* `make enable-ci` — Watchtower + GitHub Action
* `make enable-monitoring` — Prometheus + Grafana
* `make enable-ollama` — локальная LLM (Ollama)
