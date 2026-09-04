FROM caddy:2.11.4-builder AS builder

RUN xcaddy build \
	--with github.com/caddy-dns/route53@v1.6.2

FROM caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

# Caddy uses its Go HTTP stack; curl/libcurl are not required by this runtime.
RUN apk upgrade --no-cache libssl3 libcrypto3 \
	&& apk del --no-network curl libcurl

COPY front /srv/front
COPY deployment/caddy/Caddyfile /etc/caddy/Caddyfile
