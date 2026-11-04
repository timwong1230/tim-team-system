FROM python:3.12-slim

WORKDIR /app

# Cache-bust so Render rebuilds app layers after finance-repair merges.
ARG POLAR_BUILD_STAMP=2026-11-04-month-dropdown
RUN echo "polar-build ${POLAR_BUILD_STAMP}"

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
