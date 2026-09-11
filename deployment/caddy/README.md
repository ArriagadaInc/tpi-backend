# Caddy Route53 DNS-01

This directory defines the custom Caddy image used for DEV GREEN.

## Purpose

The image is built from Caddy 2.11.4 with the `caddy-dns/route53` module enabled so ACME DNS-01 challenges can be completed against Route53 before any DNS cutover.

## Operational model

- DNS-01 is used for `dev.tupensioninteligente.cl` and
  `backoffice.dev.tupensioninteligente.cl`.
- The Caddy container must not use AWS access keys.
- AWS credentials are provided through the EC2 / Elastic Beanstalk instance role.
- Route53 permissions are intentionally minimal and limited to the ACME TXT records required for these hostnames.

## Hostnames

- `dev.tupensioninteligente.cl`
- `backoffice.dev.tupensioninteligente.cl`

The public delegated hosted zone is `dev.tupensioninteligente.cl.`. Its ID is
supplied at runtime through `TPI_ROUTE53_HOSTED_ZONE_ID`; the Caddy image does
not contain a hosted zone ID.

