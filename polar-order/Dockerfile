FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data/menu.json ./data/menu.json
COPY static ./static
COPY templates ./templates

ENV POLAR_DATA_DIR=/data
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /data/receipts

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
