FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MIETTE_DONNEES=/data

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY miette ./miette
RUN pip install . \
 && useradd --system --uid 10001 --no-create-home miette \
 && mkdir /data && chown miette /data

USER miette
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/healthz', timeout=3)"
CMD ["uvicorn", "miette.app:app", "--host", "0.0.0.0", "--port", "8090", "--no-server-header"]
