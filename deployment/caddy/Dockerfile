FROM caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648

# Caddy uses its Go HTTP stack; curl/libcurl are not required by this runtime.
RUN apk del --no-network curl libcurl

COPY front /srv/front
COPY deployment/caddy/Caddyfile /etc/caddy/Caddyfile
