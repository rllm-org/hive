FROM python:3.12-slim

RUN pip install --no-cache-dir hive-evolve

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://releases.rivet.dev/sandbox-agent/0.4.x/install.sh | sh
