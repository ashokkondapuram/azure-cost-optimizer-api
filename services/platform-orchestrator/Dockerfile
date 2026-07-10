FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY packages/costoptimizer-core /app/packages/costoptimizer-core
RUN pip install --no-cache-dir -e /app/packages/costoptimizer-core
COPY app /app/app
COPY data /app/data
COPY services/platform-orchestrator /app/services/platform-orchestrator
ENV PORT=8012
WORKDIR /app/services/platform-orchestrator/src
CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8012"]
