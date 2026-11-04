# syntax=docker/dockerfile:1
FROM python:3.10-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY requirements.lock.txt pyproject.toml ./
COPY --from=python_common . /shared
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install -r requirements.lock.txt setuptools==84.0.0 wheel==0.48.0 && \
    python -m pip install --no-deps --no-build-isolation /shared
COPY . .

FROM python:3.10-slim AS production
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SERVICE_HOST=0.0.0.0
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app
RUN useradd --uid 10001 --create-home app
USER app
CMD ["python", "-m", "app.worker"]
