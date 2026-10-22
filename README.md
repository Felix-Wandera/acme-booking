# Clinic Appointment Booking API — System Design

[![CI/CD Pipeline](https://github.com/Felix-Wandera/acme-booking/actions/workflows/ci.yml/badge.svg)](https://github.com/Felix-Wandera/acme-booking/actions/workflows/ci.yml)

**Facility Name:** Acme Hospital Clinic 
**Status:** MVP Implementation  
**Proposed stack:** FastAPI, PostgreSQL, SQLAlchemy 2.x, Alembic, pytest, GitHub Actions, Railway  
**Production deployment stack:** Docker, Coolify (VPS), GitHub Actions  

**Public Deployment URL:** `https://clinic-booking.wandera.online`  

**Interactive API Docs:** `https://clinic-booking.wandera.online/docs`

**ReDoc Documentation:** `https://clinic-booking.wandera.online/redoc`

## 1. Overview 

The system exposes a REST API that allows patients to view a doctor's available 30-minute appointment slots, book a slot, cancel a booking, and reschedule an existing appointment. It is designed for a small clinic with five doctors.

The main engineering requirement is **booking consistency**: two concurrent requests must never create active appointments for the same doctor and start time. Availability calculations help clients choose a slot, but the booking endpoint must revalidate the slot inside a database transaction before confirming the booking.

The design favours a small, maintainable implementation over premature scaling. PostgreSQL is the source of truth for appointment state and enforces the key booking invariant.

## 2. Scope and assumptions

### In scope

- Store doctors, patients, recurring doctor working hours, appointments, and blocked periods.
- Return available 30-minute slots for a doctor on a requested date.
- Book, cancel, and reschedule appointments.
- Return a patient's upcoming appointments, sorted by start time.
- Validate requests and return meaningful HTTP status codes and error messages.
- Include automated tests, a public deployment, and a CI/CD pipeline.

### Assumptions

1. The clinic has five doctors. A standard shift is eight hours, giving a theoretical maximum of 16 slots per doctor per day, or 80 appointments per clinic day. At approximately 312 operating days a year, that is about 25,000 appointment slots annually.
2. Each appointment lasts exactly 30 minutes. Start times must align to `:00` or `:30`, with seconds and microseconds set to zero.
3. Operating hours use the `Africa/Nairobi` timezone. Appointment instants are stored in PostgreSQL as `TIMESTAMPTZ`. Availability dates are interpreted as calendar dates in `Africa/Nairobi`.
4. Working hours repeat weekly. A doctor may have more than one working interval on a day, for example `09:00–12:00` and `14:00–17:00`. Overnight shifts are not supported in this MVP.
5. Empty appointment slots are not pre-created. The availability endpoint generates slots from working hours and filters out booked or blocked periods.
6. A booking must be at least one hour in the future. This implements the assessment's bonus booking-buffer requirement.
7. Appointments cannot be cancelled or rescheduled after their start time. A cancelled appointment cannot be rescheduled. A completed appointment is not an active booking.
8. Doctors are deactivated rather than deleted when historical appointments must be retained. Doctor and patient foreign keys prevent deleting records that are still referenced.
9. Authentication and patient-level authorization are not specified in the assessment and are outside this MVP's implementation scope. Use synthetic data in the public demo. The API must not be treated as suitable for real patient information until authentication, authorization, and appropriate privacy controls are added.

## 3. Architecture

```text
Client / API consumer
        |
        v
FastAPI REST endpoints
        |
        v
Booking service
  - business-rule validation
  - transaction boundaries
  - consistent lock order
        |
        v
PostgreSQL
  - persisted appointment state
  - foreign keys and check constraints
  - partial unique index
  - row-level locks
```

### Components

- **FastAPI:** Defines the REST endpoints and request/response schemas. Pydantic validates incoming data and produces the OpenAPI specification.
- **Booking service:** Contains the scheduling rules and coordinates database transactions. The API layer should not contain the booking algorithm itself.
- **PostgreSQL:** Stores the authoritative state and enforces data integrity. Transactions, row-level locks, and a partial unique index protect booking operations across multiple application requests or replicas.
- **SQLAlchemy 2.x:** Provides database access and transaction management. Synchronous SQLAlchemy sessions are sufficient for this low-volume workload; endpoints that use them will be regular `def` handlers rather than blocking database calls inside `async def` handlers.
- **Alembic:** Manages schema migrations so database changes are reproducible across local development and deployment.
- **Railway:** Hosts the API and PostgreSQL database for the assessment. Configuration is provided through environment variables.
- **GitHub Actions:** Runs automated tests for pull requests. Merging a reviewed change into `main` triggers deployment through Railway's configured branch deployment.
- **Database seed script (`seed.py`):** Pre-populates the 5 clinic doctors, default working hours, recurring lunch breaks, and sample patients to provide an immediate out-of-the-box working environment for reviewers and deployment demos.



## 4. Data model

UUID primary keys are used for public-facing entities. All foreign keys and required fields should be declared explicitly. Timestamps such as `created_at` and `updated_at` are stored consistently in UTC by the database/application configuration.

### `Doctor`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `name` | String | Required |
| `is_active` | Boolean | Defaults to `true`; inactive doctors cannot receive new bookings |
| `created_at` | TIMESTAMPTZ | Creation time |

A doctor can have multiple working-hour rules, appointments, and blocked periods.

### `DoctorWorkingHours`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `doctor_id` | UUID | Foreign key to `Doctor` |
| `day_of_week` | Small integer | Monday `0` through Sunday `6` |
| `start_time` | TIME | Inclusive start of the working interval |
| `end_time` | TIME | Exclusive end of the working interval; must be after `start_time` |

A doctor may have multiple intervals on the same weekday. The service validates that a proposed 30-minute appointment fits completely inside one interval. Working-hour intervals for the same doctor and weekday must not overlap.

### `Patient`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `name` | String | Required |
| `phone_number` | String | Required for contact; normalize consistently if uniqueness is needed |
| `created_at` | TIMESTAMPTZ | Creation time |



### `Appointment`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `doctor_id` | UUID | Foreign key to `Doctor` |
| `patient_id` | UUID | Foreign key to `Patient` |
| `start_time` | TIMESTAMPTZ | Start instant; the duration is fixed at 30 minutes |
| `status` | Enum | `BOOKED`, `CANCELLED`, or `COMPLETED` |
| `cancellation_reason` | Text, nullable | Required when cancelling; null for other statuses |
| `created_at` | TIMESTAMPTZ | Creation time |
| `updated_at` | TIMESTAMPTZ | Last modification time |

`BOOKED` represents an active reservation. Whether a booking is upcoming is derived from `status = BOOKED` and `start_time > now`; it is not stored as a separate lifecycle status. `COMPLETED` is available for historical records, although completing appointments is not a required endpoint in this assessment.

**Database invariant:** create a partial unique index on `(doctor_id, start_time)` for rows whose status is `BOOKED`. This prevents two active bookings at the same slot for one doctor while allowing a cancelled slot to be booked again.

Conceptually:

```sql
CREATE UNIQUE INDEX uq_active_appointment_per_slot
ON appointments (doctor_id, start_time)
WHERE status = 'BOOKED';
```

Because appointment duration is fixed and all start times are restricted to 30-minute boundaries, unique doctor/start-time pairs prevent overlapping appointments under the stated assumptions. If variable durations are introduced later, use a PostgreSQL exclusion constraint on time ranges or equivalent overlap protection.

### `BlockedTime`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `doctor_id` | UUID | Foreign key to `Doctor` |
| `start_time` | TIMESTAMPTZ | Inclusive start |
| `end_time` | TIMESTAMPTZ | Exclusive end; must be after `start_time` |
| `reason` | String | For example, lunch, leave, or clinic closure |

Blocked periods are date-specific and can represent lunch breaks, leave, holidays, and temporary closures. A slot is excluded if its interval overlaps any blocked period. Time intervals follow the half-open convention `[start, end)`, so an appointment ending at 10:30 does not overlap one starting at 10:30.

### Database seeding & initial state

To satisfy the 5-doctor clinic scenario and ensure a seamless review/demo experience, the project includes an automated database seed script (`python -m app.db.seed` or `seed.py`):
- Pre-populates the 5 clinic doctors with realistic specialties and UUIDs.
- Establishes recurring weekly working hours for each doctor (e.g., Monday through Friday, 08:00–12:00 and 14:00–17:00 in `Africa/Nairobi`).
- Configures sample recurring blocked periods (such as daily 12:00–14:00 lunch breaks).
- Seeds test patients for immediate verification of booking and upcoming-appointment queries.

## 5. Booking invariants and validation

Every booking or rescheduling request must satisfy all of the following:

1. The doctor exists and is active.
2. The patient exists.
3. The requested start time contains a timezone offset, or is otherwise normalized using the documented `Africa/Nairobi` convention at the API boundary.
4. The start time is on a 30-minute boundary with zero seconds and microseconds.
5. The appointment is at least one hour in the future.
6. The appointment's entire 30-minute interval fits inside one of the doctor's working-hour intervals for that local weekday.
7. The appointment does not overlap a blocked period.
8. No other `BOOKED` appointment exists for the same doctor and start time.
9. State transitions are valid: cancelled appointments cannot be rescheduled, and appointments that have already started cannot be cancelled or rescheduled.

Availability results are advisory: a slot may be booked by another user after the availability response is generated. The booking endpoint always repeats the relevant checks within its transaction before inserting or updating an appointment.

## 6. Concurrency and transaction strategy

### Booking a slot

Application-side availability checks alone do not prevent double-booking: two requests could both observe an empty slot before either inserts an appointment. The design uses transaction-level coordination and a database constraint.

For a new booking:

1. Begin a PostgreSQL transaction using the default `READ COMMITTED` isolation level.
2. Lock the requested doctor row with `SELECT ... FOR UPDATE`. All appointment-mutating operations for that doctor follow the same lock order. This serializes booking changes for one doctor while allowing different doctors to be handled concurrently.
3. Re-read and validate the doctor's status, working hours, blocked periods, and existing active appointments after acquiring the lock.
4. Insert the appointment with status `BOOKED`.
5. Commit the transaction.
6. If the partial unique index reports a uniqueness violation, roll back and return `409 Conflict` with a slot-unavailable error.

The doctor-row lock provides a predictable transaction path for the clinic's small workload. The partial unique index remains the final database-level safeguard if a future code path fails to follow the locking protocol or concurrent requests still reach the insert.

### Cancellation

1. Read the appointment's immutable `doctor_id` to determine which doctor row to lock.
2. Begin a transaction, lock the doctor row, then lock and re-read the appointment row.
3. Confirm the appointment is `BOOKED` and has not started.
4. Set status to `CANCELLED`, store the required cancellation reason, update `updated_at`, and commit.

The appointment no longer qualifies for the partial unique index, so its slot becomes bookable again.

### Rescheduling

1. Begin a transaction, lock the appointment's doctor row, then lock and re-read the appointment.
2. Reject the request if the appointment is cancelled or has already started.
3. Validate the target start time using the same rules as a new booking, excluding the appointment being rescheduled from the conflict query.
4. Update `start_time` and `updated_at` within the same transaction.
5. Commit only if all checks and database constraints succeed. Otherwise, roll back the entire transaction so the original appointment remains unchanged.

For this MVP, rescheduling changes the time but keeps the same doctor. Moving an appointment to a different doctor can be added later with deterministic locking of both doctor rows to avoid deadlocks.

## 7. REST API

All core resource endpoints are versioned and mounted under the **`settings.API_V1_STR`** prefix (default: **`/api/v1`**). System health checks and interactive documentation reside at the root level (`/health`, `/docs`, `/redoc`).

- **API Base Prefix:** `/api/v1` (`settings.API_V1_STR`)
- **Request & Response Format:** JSON (`application/json`)
- **Datetime Representation:** ISO 8601 with explicit timezone offset (e.g., `2026-10-23T10:00:00+03:00`)
- **Reference Timezone:** `Africa/Nairobi` (EAT, UTC+03:00)

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/doctors/{doctor_id}/availability` | `GET` | Retrieve available 30-min slots for a given date |
| `/api/v1/appointments` | `POST` | Book a new 30-min appointment slot |
| `/api/v1/appointments/{id}/cancel` | `PATCH` | Cancel an active appointment with reason |
| `/api/v1/appointments/{id}/reschedule` | `PATCH` | Atomically reschedule appointment to a new slot |
| `/api/v1/patients/{patient_id}/appointments` | `GET` | List upcoming appointments for a patient (paginated) |
| `/health` | `GET` | Application and database connectivity health check |
| `/docs` | `GET` | Interactive Swagger OpenAPI documentation |

### `POST /api/v1/appointments`

Books a 30-minute slot.

**Request**

```json
{
  "doctor_id": "<doctor-uuid>",
  "patient_id": "<patient-uuid>",
  "start_time": "2026-10-23T10:00:00+03:00"
}
```

**Success:** `201 Created` with the created appointment, including its ID, doctor, patient, start time, and status.

**Possible errors:**

- `404 Not Found` — doctor or patient does not exist.
- `409 Conflict` — doctor is inactive or the slot is already booked.
- `422 Unprocessable Entity` — malformed input, invalid slot alignment, past/too-soon time, outside working hours, or overlap with blocked time.

### `GET /api/v1/doctors/{doctor_id}/availability?date=YYYY-MM-DD`

Returns available 30-minute start times for the requested calendar date in `Africa/Nairobi`.

**Example response**

```json
{
  "doctor_id": "<doctor-uuid>",
  "date": "2026-10-23",
  "timezone": "Africa/Nairobi",
  "available_slots": [
    "2026-10-23T09:00:00+03:00",
    "2026-10-23T09:30:00+03:00",
    "2026-10-23T10:00:00+03:00"
  ]
}
```

The service generates candidate times from that weekday's working intervals, then excludes slots that are in the past or inside the booking buffer, overlap a blocked period, or have a `BOOKED` appointment. Results are sorted in ascending order. A valid date with no available slots returns `200 OK` with an empty array.

**Possible errors:** `404 Not Found` if the doctor does not exist; `422 Unprocessable Entity` if the date is invalid.

### `PATCH /api/v1/appointments/{appointment_id}/cancel`

Cancels an active appointment and frees its slot.

**Request**

```json
{
  "reason": "Patient requested cancellation"
}
```

**Success:** `200 OK` with the updated appointment.

**Possible errors:** `404 Not Found` if the appointment does not exist; `409 Conflict` if it is already cancelled or has already started; `422 Unprocessable Entity` if the reason is missing or invalid.

A repeated cancellation is deliberately reported as a conflict because the assessment requires an error when an appointment has already been cancelled. The response behaviour is documented rather than described as idempotent.

### `PATCH /api/v1/appointments/{appointment_id}/reschedule`

Moves an active appointment to a different slot for the same doctor.

**Request**

```json
{
  "new_start_time": "2026-10-23T11:30:00+03:00"
}
```

**Success:** `200 OK` with the updated appointment.

**Possible errors:** `404 Not Found` if the appointment does not exist; `409 Conflict` if the new slot is taken or the appointment is cancelled; `422 Unprocessable Entity` if the target time violates scheduling rules. A failed reschedule must leave the original appointment unchanged.

### `GET /api/v1/patients/{patient_id}/appointments?limit=10&offset=0`

Bonus endpoint returning upcoming appointments for a patient, sorted by `start_time` ascending. The default page size is 10; `limit` is constrained to a reasonable range (for example, 1–100) and `offset` must be non-negative.

The result includes only appointments with `status = BOOKED` and `start_time` later than the current time. Return `404 Not Found` if the patient does not exist. An existing patient with no upcoming appointments receives `200 OK` and an empty list.

### Error response format

Business-rule errors use a consistent shape:

```json
{
  "detail": {
    "code": "SLOT_UNAVAILABLE",
    "message": "The selected slot is no longer available."
  }
}
```

Use stable machine-readable `code` values and human-readable `message` values. Request-schema validation errors should also be normalized to a documented `422` response format, either through a FastAPI validation exception handler or by documenting FastAPI's default validation response.


## 8. Testing strategy

Tests must exercise both normal behaviour and the key invariants. Use a real PostgreSQL test database for integration and concurrency tests; SQLite is not a reliable substitute for PostgreSQL row locks and partial-index behaviour.

Minimum coverage:

1. **Successful booking:** a valid available slot returns `201 Created` and persists a `BOOKED` appointment.
2. **Working-hour validation:** reject a slot outside a doctor's working intervals.
3. **Time validation:** reject past appointments, appointments inside the one-hour buffer, and start times not aligned to `:00` or `:30`.
4. **Blocked periods:** a slot overlapping a blocked interval is excluded from availability and rejected if submitted directly.
5. **Duplicate booking:** a second booking for the same doctor and start time returns a conflict.
6. **Concurrent booking race conditions:** issue simultaneous booking requests for the identical slot across multiple worker threads or tasks (using `concurrent.futures.ThreadPoolExecutor` with independent database sessions/connections). The test asserts that:
   - Exactly one request successfully acquires the doctor row lock, inserts the appointment, and receives `201 Created`.
   - All concurrent competing requests are serialized, detect the conflict during re-validation or trigger the partial unique index (`uq_active_appointment_per_slot`), and receive `409 Conflict` with a structured `SLOT_UNAVAILABLE` error payload.
   - The database maintains strict integrity with exactly one active record for that slot.
7. **Cancellation:** require a reason, store it, and verify that the cancelled slot becomes available again. A second cancellation must return a conflict.
8. **Rescheduling:** a successful reschedule moves the appointment; a failed reschedule leaves the original slot and appointment unchanged; cancelled appointments cannot be rescheduled.
9. **Availability output:** slots are ordered, timezone-aware, and exclude booked, blocked, past, and too-soon times.
10. **Patient upcoming appointments:** results are sorted ascending, exclude cancelled and past appointments, and respect pagination.

Use a controllable clock or inject the current time into service-level functions where useful, so time-based tests are deterministic.


## 9. Key trade-offs and future extensions

- **Dynamic availability instead of pre-generated slots:** reduces stored data and avoids maintaining empty-slot records. The trade-off is that availability is calculated on request and can become stale immediately; booking-time validation handles that race.
- **Per-doctor row locking:** intentionally limits simultaneous appointment mutations for one doctor. With only five doctors and low daily volume, the simplicity is worth more than fine-grained locking. Different doctors can still be processed concurrently.
- **Database constraint as a final safeguard:** application validation provides useful errors, while the partial unique index enforces the invariant independently of application code.
- **Single operating timezone:** keeps the MVP straightforward. If the product expands to clinics in different regions, store a timezone per clinic or doctor and generate local operating dates accordingly.
- **No authentication in the assessment MVP:** avoids adding requirements not present in the prompt, but means the public demo must use synthetic data. A production version would require authentication, authorization, audit logging, rate limiting, and careful handling of health-related personal data.
- **Fixed duration:** simplifies overlap checks. Variable appointment types and durations would require interval-based conflict enforcement and likely a richer scheduling model.

## 10. Local development and testing

### Prerequisites
- Python 3.13+
- PostgreSQL 16+ running locally or in Docker

### Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Felix-Wandera/acme-booking.git
   cd acme-booking
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Copy `.env.example` to `.env` and set your PostgreSQL credentials:
   ```env
   PROJECT_NAME="Acme Hospital Clinic Booking System"
   DATABASE_URL="postgresql+psycopg://postgres:<password>@localhost:5432/acme_booking"
   TIMEZONE="Africa/Nairobi"
   ```

5. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Seed baseline clinic data (5 doctors, schedules, patients):**
   ```bash
   python seed.py
   ```
   *(The seed script is strictly idempotent; use `python seed.py --reset` to clear and reset).*

7. **Run the automated test suite:**
   ```bash
   pytest -v
   ```

8. **Start the local development server:**
   ```bash
   uvicorn main:app --reload
   ```
   - Root Health Check: `http://127.0.0.1:8000/health`
   - API V1 Base Path: `http://127.0.0.1:8000/api/v1`
   - Interactive Swagger Documentation: `http://127.0.0.1:8000/docs`
   - ReDoc Documentation: `http://127.0.0.1:8000/redoc`


## 11. Deployment and CI/CD

### Architecture
The application is containerized with Docker and hosted on a Virtual Private Server (VPS) managed through **Coolify** behind a Traefik reverse proxy with automated SSL.

- **Container Engine:** Docker (`python:3.13-slim` base image)
- **Startup Lifecycle (`entrypoint.sh`):**
  1. Checks database connectivity and waits for PostgreSQL to become ready.
  2. Executes `alembic upgrade head` to run schema migrations automatically.
  3. Executes `python seed.py` to idempotently ensure baseline clinic data is present.
  4. Starts Uvicorn serving on port `8000`.

### CI/CD Pipeline (GitHub Actions)
The automated workflow is defined in `.github/workflows/ci.yml`:

- **Pull Request Automation:** Every Pull Request targeting `main` or `staging` automatically spins up a real `postgres:17-alpine` service container, runs database migrations, and executes all 30 automated tests (`pytest -v`). PR merges are blocked if any test fails.
- **Designated Deployment Branch (`staging`):**
  - When changes are merged into the `staging` branch, the `deploy` job triggers a deployment webhook to Coolify.
  - Coolify pulls the latest code from `staging`, builds the Docker image, applies migrations, and auto-deploys the service with zero downtime.

### Live Application URL
- **Public Base URL:** [https://clinic-booking.wandera.online](https://clinic-booking.wandera.online)
- **API V1 Base Path:** [https://clinic-booking.wandera.online/api/v1](https://clinic-booking.wandera.online/api/v1)
- **Interactive Swagger / OpenAPI Docs:** [https://clinic-booking.wandera.online/docs](https://clinic-booking.wandera.online/docs)
- **ReDoc Documentation:** [https://clinic-booking.wandera.online/redoc](https://clinic-booking.wandera.online/redoc)
- **Health Check Endpoint:** [https://clinic-booking.wandera.online/health](https://clinic-booking.wandera.online/health) 

