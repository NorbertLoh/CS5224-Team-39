# syntax=docker/dockerfile:1
FROM document
COPY --chown=app:app setup.py /tools/setup.py
ENTRYPOINT ["python", "/tools/setup.py"]
