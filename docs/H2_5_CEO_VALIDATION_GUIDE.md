# H2.5 CEO Validation Guide

This guide is for AWS DEV validation only. Technical staff will provide the
URLs, an approved username, and a temporary password by a separate secure
channel. Do not share passwords, screenshots containing credentials, or real
client data.

## As a prospect

1. Open the public DEV URL.
2. Confirm the landing page and form are available without signing in.
3. Register one lead using fictional data only.
4. Confirm the successful submission message and DEV notification email.

## As an internal user

1. Open the private backoffice URL.
2. Sign in with the supplied temporary credentials.
3. Find the fictional lead and review its detail and traceability.
4. Use the explicit DEV cleanup action to delete the fictional test lead.
5. Confirm the lead no longer appears.
6. Select `Cerrar sesion` and confirm the private area is blocked again.

SimpleDevAuth is a temporary DEV-only mechanism. Production will use managed
HTTPS and a professional identity provider.

## Local rehearsal

For a local rehearsal, technical staff provides `http://tpi.localhost` and
`http://backoffice.tpi.localhost` plus a locally generated test credential.
Use synthetic data only. The public landing must remain available without
login; the private URL must require login and return to that state after logout.
Local cleanup is performed by resetting the demo database, not by weakening the
AWS DEV cleanup safeguard.
