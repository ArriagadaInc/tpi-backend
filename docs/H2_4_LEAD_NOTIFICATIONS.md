# H2.4 - Lead Notifications

## Objective

H2.4 adds a small, extensible post-commit notification capability. Its first
consumer is an Amazon SNS email subscription, but the TPI core publishes a
safe event rather than knowing about email.

```
Streamlit or future web frontend
        |
SolicitudService
        |
SolicitudRepository -> PostgreSQL COMMIT
        |
LeadCreatedEvent -> LeadEventPublisher -> SNS topic
        |                                  |
        |                                  +-- Email (H2.4)
        |                                  +-- SMS (future)
        |                                  +-- Lambda/WhatsApp adapter (future)
```

`SolicitudRepository` and Streamlit do not import boto3 or SNS. The service
publishes only after `create_solicitud()` returns, which is after the
repository transaction commits.

## Event contract

`app.notifications.events.LeadCreatedEvent` is an immutable, versioned
contract. It has an independent UUID `event_id` and a timezone-aware UTC
`occurred_at` timestamp.

```json
{
  "schema_version": "1.0",
  "event_type": "lead.created",
  "event_id": "<uuid>",
  "lead_id": "<uuid>",
  "occurred_at": "<UTC ISO-8601>",
  "environment": "aws-dev",
  "source": "tpi-backoffice"
}
```

It never includes RUT, name, customer email, phone, date of birth, AFP,
balance, comments, consent, or raw payload.

## Publisher abstraction

`LeadEventPublisher` is a one-method protocol returning `PublishResult` with
one of `published`, `disabled`, or `failed`. H2.4 provides:

- `DisabledLeadEventPublisher`: safe default when notifications are off.
- `MisconfiguredLeadEventPublisher`: safe failure when enabled without a topic.
- `SnsLeadEventPublisher`: the SNS adapter.

`SolicitudService` depends only on the protocol and accepts a fake publisher
in tests. Adding a future channel is an adapter or SNS subscriber change; it
does not require changing the repository, form, or lead creation flow.

## SNS and email

The DEV Standard topic is:

```
arn:aws:sns:us-east-2:821656895812:tpi-dev-lead-created
```

The topic name is event-oriented, not email-oriented. The approved email
subscription is intentionally not recorded in this repository. SNS sends its
standard confirmation message to that mailbox; it must show `Confirmed` before
an AWS smoke test can assert email delivery.

SNS receives `MessageStructure=json` with three PII-free renderings:

- `default`: serialized `LeadCreatedEvent` JSON.
- `email`: operational text with environment, lead UUID, and UTC timestamp.
- `sms`: a short future SMS representation. No SMS subscription is created.

No WhatsApp, Lambda, SMS, SES, SQS, EventBridge, or retry worker is created in
H2.4.

## Configuration

Safe defaults are versioned in `Settings`, `.env.example`, and Elastic
Beanstalk configuration:

```dotenv
LEAD_NOTIFICATIONS_ENABLED=false
LEAD_NOTIFICATION_TOPIC_ARN=
```

For the approved environment only, set the following Elastic Beanstalk
properties outside the versioned configuration:

```text
LEAD_NOTIFICATIONS_ENABLED=true
LEAD_NOTIFICATION_TOPIC_ARN=arn:aws:sns:us-east-2:821656895812:tpi-dev-lead-created
```

The topic ARN is never hardcoded in Python. The recipient belongs exclusively
to the SNS subscription, never to application configuration or Git.

## IAM and privacy

The instance role `tpi-backoffice-dev-ec2-role` has the inline policy
`tpi-backoffice-dev-publish-lead-created`, versioned at
`deployment/iam/tpi-backoffice-dev-publish-lead-created.json`. It grants only:

```json
{
  "Effect": "Allow",
  "Action": "sns:Publish",
  "Resource": "arn:aws:sns:us-east-2:821656895812:tpi-dev-lead-created"
}
```

It does not grant topic creation, subscriptions, deletion, `sns:*`, wildcard
resources, or access to `tpi/dev/database-admin-password`. Existing database
secrets and PostgreSQL privileges are unchanged.

Logs record only `event_id`, `lead_id`, environment, provider, outcome, and
SNS message ID on success. They do not record payloads, PII, credentials, or
AWS tokens.

## Failure semantics

Lead persistence is primary. Publication is best effort after a successful
database commit:

```text
COMMIT succeeds + SNS fails = lead remains registered
```

The user continues to receive the normal registration success response. SNS
errors are logged safely and do not trigger a rollback of the already committed
lead. This intentionally provides at-most-once best-effort delivery in H2.4.

For a future higher-criticality environment, replace direct publication with:

```text
Service -> Transactional Outbox -> Worker -> SNS
```

That change preserves the Streamlit, repository, and lead-creation contracts.

## Tests and validation

Unit, integration, E2E regression, and security tests cover event shape,
timezone-aware timestamps, independent IDs, no PII in event or renderings,
disabled/misconfigured behavior, SNS success/failure, post-commit publication,
and the rule that publisher failure does not lose the lead. IAM tests reject
wildcards and administrative-secret access.

The full local H2.4 suite passed with 226 tests and 88.49% coverage before AWS
publication configuration. The CI gate requires at least 85% coverage.

## AWS deployment and smoke test

1. Verify the subscription is `Confirmed`.
2. Deploy the reviewed source bundle to `tpi-backoffice-dev`.
3. Set the two Elastic Beanstalk properties above only on that environment.
4. Wait for `Ready` and `Green`.
5. Register one fictitious lead from the restricted DEV URL.
6. Verify its row in PostgreSQL and the SNS email lead UUID, with no PII.
7. Review CloudWatch logs for the safe publication event.
8. Delete the fictitious lead using the H2.3 guarded cleanup and verify RDS.

## Rollback

Disable notifications immediately without affecting lead creation or H2.3:

1. Set `LEAD_NOTIFICATIONS_ENABLED=false` on `tpi-backoffice-dev`.
2. Restart or redeploy the environment if required.
3. Optionally remove the `tpi-backoffice-dev-publish-lead-created` inline role
   policy after traffic has stopped.

The SNS topic may remain for diagnosis. Do not delete RDS, modify database
grants, or remove the existing database-secret policy as part of this rollback.

## Limitations

The current direct SNS design has no transactional outbox, durable retry, or
delivery guarantee. A published email is not retracted if a fictitious lead is
later deleted. HTTPS, identity-based DEV access, SMS, WhatsApp, and production
notification operations remain out of scope for H2.4.
