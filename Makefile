enable-rag:
	cp extras/compose.rag.yml docker-compose.override.yml
	docker compose up -d --build

enable-sandbox:
	cp extras/compose.sandbox.yml docker-compose.override.yml
	docker compose up -d --build

enable-ci:
	mkdir -p .github/workflows
	cp extras/docker.yml .github/workflows/docker.yml
	cp extras/compose.watchtower.yml docker-compose.override.yml
	docker compose up -d --build

enable-monitoring:
	cp extras/compose.monitoring.yml docker-compose.override.yml
	docker compose up -d --build

enable-ollama:
	cp extras/compose.ollama.yml docker-compose.override.yml
	docker compose up -d --build
run:
	uvicorn main:app --host 0.0.0.0 --port 8000 --reload
