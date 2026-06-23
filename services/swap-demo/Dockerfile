FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling

# swap-demo uses src-layout with pythonpath=["src"]: the packages inside src/
# (bootstrap, entrypoints, …) must be importable directly without a "src." prefix.
# pytest achieves this via pythonpath=["src"] in pyproject.toml; uvicorn needs
# PYTHONPATH set explicitly to the same directory.
COPY src/ src/
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src

EXPOSE 8005

CMD ["uvicorn", "entrypoints.http.main:app", "--host", "0.0.0.0", "--port", "8005"]
