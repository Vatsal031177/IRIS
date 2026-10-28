FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ ./services/
COPY tests/ ./tests/
COPY sql/ ./sql/

ENV PYTHONPATH=/app

CMD ["python", "-m", "services.orchestrator.main", "--mode", "fixture"]
