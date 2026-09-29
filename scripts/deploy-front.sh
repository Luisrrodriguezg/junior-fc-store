#!/usr/bin/env bash
# Publishes the storefront. junior-fc.html is served as /junior.html (the Cognito post-login page).
# Targeted cp + invalidation on purpose: never `s3 sync` this folder (it holds the legacy scrape).
set -euo pipefail
cd "$(dirname "$0")/.."

aws s3 cp junior-fc.html s3://adidas-junior-luisrro/junior.html --content-type "text/html; charset=utf-8"
aws cloudfront create-invalidation --distribution-id E1SZ96N9BLQYYV --paths /junior.html \
  --query "Invalidation.[Id,Status]" --output text
echo "Publicado: https://d2c5kwdca3zpk9.cloudfront.net/junior.html (la invalidación tarda ~1 min)"
