# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately through GitHub's
[**Report a vulnerability**](https://github.com/delmalih/saas-genai-starter/security/advisories/new)
flow (the *Security* tab → *Report a vulnerability*), or by email to
**da.elmalih@gmail.com**.

Please include:

- a description of the issue and its impact,
- steps to reproduce (a proof of concept if possible),
- affected component (web / api / infra) and version or commit.

You can expect an acknowledgement within a few days. Once the issue is
confirmed and fixed, we'll coordinate a disclosure timeline with you and credit
you if you wish.

## Supported versions

This is a starter template, not a versioned product: security fixes land on
`main`. If you have deployed your own fork, pull the relevant fix into it.

## Scope and expectations

This repository ships a **bring-your-own-key** design and several security
properties by construction — they're the kinds of things worth a report if you
find a hole:

- Tenant isolation is enforced in the repository layer; cross-tenant data access
  would be a serious bug.
- Organization API keys are Fernet-encrypted at rest and write-only through the
  API (only `is_set` + last 4 chars are ever returned).
- Internal job endpoints verify Cloud Tasks OIDC tokens; the admin surface is an
  email allowlist returning 404 to non-admins.

When deploying your own instance, the usual operator responsibilities apply:
keep `SECRET_ENCRYPTION_KEY`, database and provider credentials out of source
control, rotate them if leaked, and run behind HTTPS.
