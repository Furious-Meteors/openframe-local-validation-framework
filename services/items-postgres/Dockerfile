FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling

COPY src/ src/
RUN pip install --no-cache-dir -e .

EXPOSE 8001

CMD ["uvicorn", "src.entrypoints.http.main:app", "--host", "0.0.0.0", "--port", "8001"]
