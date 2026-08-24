FROM python:3.12-slim

WORKDIR /app

# System deps for weasyprint (PDF generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libcairo2 && \
    rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --no-cache-dir .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

CMD ["./docker-entrypoint.sh"]
