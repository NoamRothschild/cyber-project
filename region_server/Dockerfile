# Build from project root: docker build -f region_server/Dockerfile .
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python setup_dev.py

WORKDIR /app/region_server

CMD ["python", "region_server.py"]
