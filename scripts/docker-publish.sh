#!/usr/bin/env bash
# Builds the boletería image and pushes it to Docker Hub (public repo luisrro21/jfc-boleteria).
# Requires that you already ran `docker login -u luisrro21` yourself.
#
#   scripts/docker-publish.sh 1.0.0
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:?uso: scripts/docker-publish.sh <version>   (ej. 1.0.0)}"
IMAGEN="docker.io/${DOCKERHUB_USER:-luisrro21}/jfc-boleteria"

# linux/amd64: the architecture of the OpenShift Sandbox nodes.
docker build --platform linux/amd64 -t "$IMAGEN:$VERSION" -t "$IMAGEN:latest" services/boleteria
docker push "$IMAGEN:$VERSION"
docker push "$IMAGEN:latest"

echo
echo "Publicada: $IMAGEN:$VERSION"
echo "En OpenShift, actualiza la imagen del Deployment 'boleteria' a esa etiqueta (ver openshift/README.md)."
