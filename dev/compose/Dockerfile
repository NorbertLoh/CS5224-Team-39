# syntax=docker/dockerfile:1
FROM document
USER root
RUN mkdir -p /reset-state && chown app:app /reset-state
USER app
COPY --chown=app:app setup.py /tools/setup.py
ENTRYPOINT ["python", "/tools/setup.py"]
