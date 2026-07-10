FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY packages/costoptimizer-core /app/packages/costoptimizer-core
RUN pip install --no-cache-dir -e /app/packages/costoptimizer-core
COPY app /app/app
COPY services/platform-gateway /app/services/platform-gateway
ENV PORT=8080
WORKDIR /app/services/platform-gateway/src
CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8080"]
