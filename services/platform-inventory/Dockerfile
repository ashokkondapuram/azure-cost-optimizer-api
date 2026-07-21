# syntax=docker/dockerfile:1
ARG PYTHON_BASE_IMAGE=costoptimize/python-base:dev

FROM ${PYTHON_BASE_IMAGE} AS dev
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*
COPY app /app/app
COPY data/kafka-topics.yaml /app/data/kafka-topics.yaml
COPY data/kafka/schemas /app/data/kafka/schemas
COPY it_services /app/it_services
COPY services/platform-inventory /app/services/platform-inventory
ENV PORT=8012 \
    KAFKA_TOPICS_MANIFEST=/app/data/kafka-topics.yaml \
    KAFKA_SCHEMAS_MANIFEST=/app/data/kafka/schemas/schemas-manifest.yaml \
    KAFKA_SCHEMAS_DIR=/app/data/kafka/schemas
WORKDIR /app/services/platform-inventory/src
CMD ["sh", "-c", "exec uvicorn main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8012}"]

FROM ${PYTHON_BASE_IMAGE} AS prod
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*
COPY app /app/app
COPY data /app/data
COPY it_services /app/it_services
COPY services/platform-inventory /app/services/platform-inventory
ENV PORT=8012 \
    KAFKA_TOPICS_MANIFEST=/app/data/kafka-topics.yaml \
    KAFKA_SCHEMAS_MANIFEST=/app/data/kafka/schemas/schemas-manifest.yaml \
    KAFKA_SCHEMAS_DIR=/app/data/kafka/schemas
WORKDIR /app/services/platform-inventory/src
CMD ["sh", "-c", "exec uvicorn main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8012}"]
