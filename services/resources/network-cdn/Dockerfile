FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY packages/costoptimizer-core /app/packages/costoptimizer-core
RUN pip install --no-cache-dir -e /app/packages/costoptimizer-core

COPY app /app/app
COPY data /app/data
COPY services/resources/network-cdn/src /app/services/resources/network-cdn/src

ENV PORT=8126
WORKDIR /app/services/resources/network-cdn/src
CMD ["uvicorn", "service_app:app", "--host", "127.0.0.1", "--port", "8126"]
