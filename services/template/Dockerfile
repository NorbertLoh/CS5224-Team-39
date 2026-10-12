# syntax=docker/dockerfile:1
FROM python:3.10-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1

FROM base AS build
WORKDIR /build
COPY . .
RUN python -m pip install --no-cache-dir -c requirements.lock.txt setuptools wheel && \
    python -m pip install --no-cache-dir --no-build-isolation \
      --prefix=/install -c requirements.lock.txt .

FROM base AS development
WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir -r requirements.lock.txt && \
    python -m pip install --no-deps --no-build-isolation -e .
RUN useradd --uid 10001 --create-home app
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/app", "--no-access-log"]

FROM base AS production
WORKDIR /app
COPY --from=build /install /usr/local
COPY --from=build /build /app
RUN useradd --uid 10001 --create-home app
USER app
ENV SERVICE_HOST=0.0.0.0 SERVICE_PORT=8000 SERVICE_ENVIRONMENT=production
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"
CMD ["python", "-m", "app"]
