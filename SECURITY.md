# Security Policy

This repository is a **portfolio demonstration**, not a production multi-tenant service.

## Supported versions

Only the latest `master` branch of this local MVP is maintained for demonstration purposes.

## Reporting a vulnerability

If you discover a security issue in this codebase:

1. **Do not** open a public GitHub issue that includes exploit details or sample documents containing real personal data.
2. Contact the repository owner privately (via the GitHub account that publishes the project) with a description, reproduction steps using **fictional** data only, and impact assessment.
3. Allow reasonable time for a response before public disclosure.

## Scope notes

- The MVP has **no authentication**. Treat any networked exposure as high risk.
- File validation is not malware scanning.
- Temporary deletion uses ordinary filesystem unlink, not secure erase.
- Dependency findings and accepted risks are tracked in [docs/dependency-audit.md](docs/dependency-audit.md) and [docs/security.md](docs/security.md).

Thank you for helping keep the demonstration honest and safe.
