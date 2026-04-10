FROM rivetdev/sandbox-agent:0.4.2-full

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages hive-evolve
