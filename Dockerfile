FROM node:22-bookworm-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates bash \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && ln -s /opt/venv/bin/python /usr/local/bin/python \
    && ln -s /usr/local/bin/node /usr/bin/node
ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && /usr/sbin/groupadd --gid 10001 marka \
    && /usr/sbin/useradd --uid 10001 --gid 10001 --home-dir /state --no-create-home marka \
    && mkdir -p /state /run/marka /workspace \
    && chown -R marka:marka /state /run/marka /workspace

FROM base AS sandbox
ENV MARKA_SANDBOX_CONTAINER=1 MARKA_SANDBOX_SOCKET=/run/marka/runner.sock
USER 10001:10001
ENTRYPOINT ["python", "-m", "marka.sandbox"]

FROM base AS bot
ARG CODEX_VERSION=0.144.1
RUN npm install --global --ignore-scripts @openai/codex@${CODEX_VERSION} \
    && codex --version
COPY scripts ./scripts
COPY tests ./tests
ENV MARKA_DATA=/state MARKA_SANDBOX_SOCKET=/run/marka/runner.sock MARKA_EVAL_TESTS=/app/tests
USER 10001:10001
ENTRYPOINT ["marka"]
CMD ["run"]
