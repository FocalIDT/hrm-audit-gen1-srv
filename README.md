# 🧾 HRM Audit Log Service

Immutable, tenant-scoped audit trail for the HRM system: **who** did **what**, **when**, to **which
employee**, **what changed** (previous → new), **why**, and **which request/transaction** it relates to.
Readable only by the **SUPER ADMIN** of each company.

---

## How it fits together

```
Browser ──► Orchestrator ──► HRM services (employee, leave, payslip, ...)
               │  app/audit/middleware.py
               │   1. matches POST/PUT/PATCH/DELETE against the rule catalog (app/audit/catalog)
               │   2. snapshots previous state where needed (e.g. GET /employee/get/{id})
               │   3. lets the request run unchanged, reads the response
               │   4. builds events in the background, POSTs them here (X-Audit-Service-Key)
               ▼
        Audit service  ──►  MySQL: audit_logs, audit_log_changes, audit_chain_heads
               ▲
Browser (super admin) ──► Orchestrator /api/v1/audit/* ──► read API (bearer token)
```

Capture lives in the orchestrator because every UI request already passes through it, so every
module is covered without changing each microservice. Auditing never blocks or fails a business
request: lookups are time-boxed, delivery is retried in the background, and events that still cannot be
delivered are written to the orchestrator log as `AUDIT_DELIVERY_FAILED {json}` for replay.

## Guarantees

| Requirement | How |
| --- | --- |
| Tenant isolation | Tenant = JWT `client_id`, taken from the token, never from input. Every read filters on it. |
| Super admin only | Read API checks the token with the user manager and requires role `SUPER ADMIN` (orchestrator checks too). |
| Unforgeable | Writes need `X-Audit-Service-Key`, which browsers never hold. Browser-only actions (letter generation) go through an allow-listed orchestrator endpoint that always attributes them to the token's user. |
| Immutable | No update/delete API. Each row stores `prev_hash` + `record_hash` (SHA-256 chain per tenant); `GET /audit/integrity/verify` detects any edit, deletion or gap. On MySQL, startup also installs triggers rejecting UPDATE/DELETE (best effort — needs the TRIGGER privilege). |
| Idempotent | `event_uuid` is unique; re-delivered events are counted as duplicates, not stored twice. |
| Numbering | `AUD-000125`: gap-free per tenant, assigned under a row lock on `audit_chain_heads`. |

## API (`/api/v1/audit`)

| Method | Path | Who | Purpose |
| --- | --- | --- | --- |
| POST | `/events` | service key | Ingest a batch of events |
| GET | `/logs` | super admin | List; filters `date_from, date_to, employee_id, performed_by, performed_by_role, module, category, action, status, request_id, reference_id, search`, `page`, `limit` |
| GET | `/logs/export` | super admin | Same filters as CSV (max `AUDIT_EXPORT_MAX_ROWS`) |
| GET | `/logs/{AUD-000125 \| 125}` | super admin | Detail with change rows and related events |
| GET | `/logs/{id}/report` | super admin | Detail as PDF |
| GET | `/filters` | super admin | Options for the filter bar |
| GET | `/employees/{id}/history` | super admin | Career timeline, salary growth, promotion registry, request history |
| GET | `/employees/{id}/history/report` | super admin | The same as PDF |
| GET | `/integrity/verify` | super admin | Verify the tenant's hash chain |

`search` matches employee name/code, audit ID, request/reference ID, action, performer and description.

## What is captured

The orchestrator catalog (`hrm-orchestrator-gen1-srv/app/audit/catalog/`) covers 179 endpoints across
all 19 categories. Highlights:

* **Employee update** is diffed against the record before the change and split into:
  **Promotion** (designation changed *and* salary increased), **Designation Changed**,
  **Salary Increment / Decrement / Created**, **Joining Date Changed**, **Employee Status Changed**,
  and **Employee Updated** for the remaining fields — all sharing one `correlation_id`.
* **Leave / WFH approvals** re-read the request after the workflow move, so the log shows
  *Leave Approved / Rejected* (or *Approval Recorded* for an intermediate step) with type, dates and days.
* **Payroll**: each payslip records *Payroll Calculated* plus *EPF / ETF Contribution Calculated* and
  *PAYE Calculated* with the amounts and payroll period.
* Special requests, attendance corrections, overtime approvals, documents, letters, departments,
  hierarchy/access, users/permissions/login/logout, imports and exports (including every generated report),
  and system configuration.

The UI may send `X-Audit-Reason` and `X-Audit-Reference` headers with any request to record why a change
was made and the related request/reference ID.

### Known gaps (v1)

* **Failed logins** are not recorded: the tenant is unknown before a token is issued.
* The HRM has **no EPF/ETF/PAYE payment or payroll-approval workflow** yet, so "Payment Processed /
  Cancelled" and "Payroll Approved" events have no source; statutory *calculations*, rate/rule changes,
  and payslip finalisation (status `Completed`) are recorded.
* **Employee import completion** is asynchronous in the employee service; the start (file name, task id)
  is recorded, not the per-row outcome.
* History before this service was deployed is not back-filled; the employee history page anchors the
  first known role on the employee's joining date.

## ⚙️ Environment

See `.env.example`. `USER_MANAGER_URL` and `AUDIT_SERVICE_KEY` are required; the key must match the
orchestrator's `AUDIT_SERVICE_KEY`, and the orchestrator needs `AUDIT_SERVICE_URL=http://<host>:8016/api/v1`.

## 🚀 Run

```bash
python -m venv venv && venv\Scripts\activate   # or source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8016
```

Tables (and, on MySQL, the append-only triggers) are created on startup — there are no migrations to
run. Docker: `docker compose up --build -d` (port 8016); `deploy.sh` follows the other services.

## 🧪 Tests

```bash
python -m pytest -q
```

Runs against a temporary SQLite database; the user manager is stubbed.
