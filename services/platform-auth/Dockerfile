FROM python:3.13-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
        libpq-dev \
        python3-dev \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY packages/costoptimizer-core /app/packages/costoptimizer-core
RUN pip install --no-cache-dir -e /app/packages/costoptimizer-core
COPY app /app/app
COPY data /app/data
COPY it_services /app/it_services
COPY services/platform-auth /app/services/platform-auth
ENV PYTHONPATH=/app
ENV PORT=8010
WORKDIR /app/services/platform-auth/src
CMD ["sh", "-c", "exec uvicorn main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8010}"]
