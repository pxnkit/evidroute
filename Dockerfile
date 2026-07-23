FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system evidroute && adduser --system --ingroup evidroute evidroute

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data/mini_route ./data/mini_route
COPY apps/api ./apps/api
RUN python -m pip install .

RUN mkdir -p /app/artifacts && chown -R evidroute:evidroute /app
USER evidroute

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
