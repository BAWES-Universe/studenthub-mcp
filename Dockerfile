# StudentHub MCP — read-only data layer
# Production image. Env (SH_DB_*) is injected by the platform (Coolify), never baked in.
FROM python:3.12-slim

# Non-root runtime user (least privilege)
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

# Install dependencies first (layer caching); PEP 517 resolves setuptools backend
COPY pyproject.toml ./
COPY server.py queries.py probe.py run_integration_local.py ./
RUN pip install --no-cache-dir .

# stdlib healthcheck (no curl/wget in slim image)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

USER appuser
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "server.py"]
