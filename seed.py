"""CLI script to seed the Acme Hospital Clinic database with baseline data."""

import argparse
import sys

from app.db.seed import seed_database
from app.db.session import SessionLocal

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the Acme Hospital Clinic database with doctors, schedules, patients, and sample appointments."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe all existing appointments, patients, and doctor records before seeding.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Bypass confirmation prompt when running with --reset.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reset even in production environments.",
    )

    args = parser.parse_args()

    if args.reset and not args.yes:
        confirm = input("[WARNING] This will delete ALL existing appointments, patients, and doctor schedules. Proceed? [y/N]: ")
        if confirm.strip().lower() not in ("y", "yes"):
            print("Operation aborted.")
            sys.exit(0)

    db = SessionLocal()
    try:
        print("\n[*] Seeding Acme Hospital Clinic database...")
        result = seed_database(db=db, reset=args.reset, force=args.force)
        stats = result["stats"]

        print("\n[SUCCESS] Seeding Complete!")
        print("--------------------------------------------------")
        print(f" Doctors created:        {stats['doctors_created']}")
        print(f" Working shifts created: {stats['working_hours_created']}")
        print(f" Patients created:       {stats['patients_created']}")
        print(f" Blocked periods:        {stats['blocked_times_created']}")
        print(f" Sample appointments:    {stats['appointments_created']}")
        print("--------------------------------------------------")

        print("\n[DOCTORS] Available Doctors:")
        for doc in result["doctors"]:
            print(f"  * {doc['name']}")
            print(f"    ID: {doc['id']}")

        print("\n[PATIENTS] Test Patients:")
        for pat in result["patients"]:
            print(f"  * {pat['name']} ({pat['phone']})")
            print(f"    ID: {pat['id']}")

        sample_date = result["sample_date"]
        sample_doc_id = result["doctors"][0]["id"]
        sample_pat_id = result["patients"][0]["id"]

        print("\n[EXAMPLES] Quick Test Examples:")
        print("--------------------------------------------------")
        print("1. Query Doctor Availability:")
        print(f"   curl http://127.0.0.1:8000/doctors/{sample_doc_id}/availability?date={sample_date}")
        print("\n2. Query Patient Upcoming Appointments:")
        print(f"   curl http://127.0.0.1:8000/patients/{sample_pat_id}/appointments")
        print("--------------------------------------------------\n")

    except Exception as e:
        print(f"\n[ERROR] Database seeding failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
