FROM python:3.11-slim

RUN pip install --no-cache-dir pyyaml && \
    apt-get update && apt-get install -y --no-install-recommends \
    smartmontools lsblk pciutils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/ /app/

ENV NODE_TYPE=gpu
ENV CHECK_INTERVAL=60
ENV METRICS_PORT=9101
ENV CONFIG_PATH=/etc/node-health-detector/config.yaml

EXPOSE 9101

ENTRYPOINT ["python3", "/app/agent.py"]
