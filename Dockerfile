FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY polymarket_ai/ polymarket_ai/

ENV PYTHONUNBUFFERED=1
ENV DEBUG_MODE=false
ENV LOG_LEVEL=INFO
ENV WEB_PORT=5050
ENV WEB_HOST=0.0.0.0

EXPOSE 5050

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5050/api/health', timeout=3)" || exit 1

CMD ["python", "-m", "polymarket_ai.webapp.app"]
