# Junior FC · Boletería — published as docker.io/luisrro21/jfc-boleteria, deployed on OpenShift.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
# Amazon RDS CA bundle (public), used to verify the database's TLS certificate.
COPY certs ./certs

# OpenShift runs containers with a random UID that belongs to group 0, so the app files must be
# readable by that group, and the image must not rely on running as root.
RUN chgrp -R 0 /app && chmod -R g=u /app
USER 1001

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
