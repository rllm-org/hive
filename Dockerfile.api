FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[server]"

EXPOSE 8080

CMD ["uvicorn", "hive.server.main:app", "--host", "0.0.0.0", "--port", "8080"]
