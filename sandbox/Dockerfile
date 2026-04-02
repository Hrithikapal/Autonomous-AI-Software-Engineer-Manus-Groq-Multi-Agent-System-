FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx

COPY executor.py .

RUN useradd -m -u 1000 sandbox && chown -R sandbox:sandbox /app
USER sandbox

EXPOSE 8001

CMD ["uvicorn", "executor:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"]
