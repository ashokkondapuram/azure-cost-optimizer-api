# syntax=docker/dockerfile:1
ARG PYTHON_BASE_IMAGE=costoptimize/python-base:dev

FROM ${PYTHON_BASE_IMAGE} AS dev
COPY services/platform-gateway /app/services/platform-gateway
ENV PORT=8080
WORKDIR /app/services/platform-gateway/src
CMD ["sh", "-c", "exec uvicorn main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8080}"]

FROM ${PYTHON_BASE_IMAGE} AS prod
COPY services/platform-gateway /app/services/platform-gateway
ENV PORT=8080
WORKDIR /app/services/platform-gateway/src
CMD ["sh", "-c", "exec uvicorn main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8080}"]
