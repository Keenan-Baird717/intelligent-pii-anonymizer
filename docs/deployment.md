# Deployment readiness — local MVP vs production

This project is verified as a **local Docker Compose demonstration**. It is **not**
production-ready and was not deployed to a cloud environment as part of Phase 9.

---

## What the MVP provides today

- `docker compose up --build` for web + API + PostgreSQL on `127.0.0.1`
- Temporary uploads with TTL and delete-now
- Security headers, CORS allow-list, trusted hosts, concurrency caps
- Non-root containers, `cap_drop: ALL`, read-only root filesystem + `tmpfs /tmp`
- Dependency audit gates in CI

---

## Required for a real deployment (not implemented)

| Area | Why it is required |
|------|--------------------|
| TLS termination | MVP binds HTTP on localhost only |
| Authentication | Opaque job UUIDs are not access control |
| Authorization | Any client that learns a UUID can act on that job |
| Secret management | Compose `.env` is for local demos |
| Private networking | API must not be publicly reachable without auth |
| Managed PostgreSQL | Backups, encryption, least-privilege roles |
| Secure temporary storage | Encrypted volumes; consider secure delete policies |
| Distributed rate limiting | Current limits are per API process |
| Coordinated cleanup | In-process TTL assumes a single API instance |
| Malware scanning / sandboxing | Signature checks are not disarming |
| Monitoring and alerting | Request IDs exist; no APM/alerting stack |
| Privacy-aware backups | Avoid backing up raw upload volumes |
| Incident response | No runbooks or on-call process in-repo |
| Multi-tenant isolation | Single shared temp store and database |

See [security.md](security.md) § production requirements and [privacy.md](privacy.md).

---

## Optional Compose notes (local only)

Keep `ENVIRONMENT=development` and `ENABLE_HSTS=false` for local HTTP.

If you experiment with a reverse proxy in front of Compose:

- Terminate TLS at the proxy
- Do not publish Postgres
- Keep API/web bound to localhost or a private network
- Do not set `DEBUG=true` outside controlled local debugging
- Do not weaken CORS to `*`

No cloud accounts, paid resources, or automatic deploys are configured by this repository.

---

## Image size expectations

The API image includes spaCy, Tesseract, and OpenCV and is on the order of **~2 GB**.
Plan pull/build time accordingly. The web image is much smaller.
