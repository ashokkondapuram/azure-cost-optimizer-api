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
COPY it_services /app/it_services
COPY services/resources/compute-disk/src /app/services/resources/compute-disk/src

ENV PORT=8108
ENV MANAGED_DISK_SPEC_PATH=/app/it_services/compute_disk/data/managed_disk_metrics_thresholds.json
WORKDIR /app/services/resources/compute-disk/src
CMD ["uvicorn", "service_app:app", "--host", "127.0.0.1", "--port", "8108"]
