FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates tini git tar \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy the Python package so it is importable as 'mark_mcp'
COPY mark_mcp /app/mark_mcp
COPY main.py /app/main.py

RUN mkdir -p /var/log/mark /srv/mark /data/mark && \
    adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /var/log/mark /srv/mark /data/mark /app

USER root

ENV PORT=8788 \
    HOST=0.0.0.0 \
    MCP_TOKEN=change-me \
    GRAPHITI_URL=http://graphiti:7878 \
    ALLOW_PATHS=/srv/mark,/var/log/mark,/data/mark \
    LOG_FILE=/var/log/mark/mark-mcp.log \
    HTTP_PROXY= \
    HTTPS_PROXY= \
    NO_PROXY=

EXPOSE 8788

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8788"]
