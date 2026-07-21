# syntax=docker/dockerfile:1
ARG PYTHON_BASE_IMAGE=costoptimize/python-base:dev

# Dev: shared deps image + service code (app/data bind-mounted in compose)
FROM ${PYTHON_BASE_IMAGE} AS dev
COPY app /app/app
COPY data/kafka-topics.yaml /app/data/kafka-topics.yaml
COPY data/kafka/schemas /app/data/kafka/schemas
COPY it_services /app/it_services
COPY services/platform-cost /app/services/platform-cost
ENV PORT=8011 \
    KAFKA_TOPICS_MANIFEST=/app/data/kafka-topics.yaml \
    KAFKA_SCHEMAS_MANIFEST=/app/data/kafka/schemas/schemas-manifest.yaml \
    KAFKA_SCHEMAS_DIR=/app/data/kafka/schemas
WORKDIR /app/services/platform-cost/src
CMD ["sh", "-c", "exec uvicorn main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8011}"]

# Prod / standalone: embed application code (no bind mounts)
FROM ${PYTHON_BASE_IMAGE} AS prod
COPY app /app/app
COPY data /app/data
COPY it_services /app/it_services
COPY services/platform-cost /app/services/platform-cost
ENV PORT=8011 \
    KAFKA_TOPICS_MANIFEST=/app/data/kafka-topics.yaml \
    KAFKA_SCHEMAS_MANIFEST=/app/data/kafka/schemas/schemas-manifest.yaml \
    KAFKA_SCHEMAS_DIR=/app/data/kafka/schemas
WORKDIR /app/services/platform-cost/src
CMD ["sh", "-c", "exec uvicorn main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8011}"]
