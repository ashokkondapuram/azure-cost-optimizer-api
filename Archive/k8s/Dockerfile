FROM python:3.12-alpine

RUN adduser -D -u 10001 agent && \
    apk add --no-cache ca-certificates tini

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

USER agent
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python", "/app/agent.py"]
