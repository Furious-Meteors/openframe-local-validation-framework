FROM python:3.11-slim

# curl for healthcheck; gcc for compiled extensions in aiokafka / motor
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling

# Copy source and install the package
COPY src/ src/
RUN pip install --no-cache-dir -e .

EXPOSE 8007

CMD ["uvicorn", "src.entrypoints.http.main:app", "--host", "0.0.0.0", "--port", "8007"]
