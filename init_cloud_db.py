"""
init_cloud_db.py - Automated Database Setup & Migration for Render Cloud Deployment

Can be run automatically in Render Start Command or manually from Render Web Shell.
Guarantees all tables (appointments, patients, doctors, notifications) exist first,
then imports initial datasets if needed.
"""

import os
import sys
import time
from pathlib import Path
from db import get_connection, is_db_connected
import init_system_db

def wait_for_db(max_retries=15, delay=2):
    """Wait for database to become reachable on cloud startup."""
    print("[DB] Verifying PostgreSQL connection...")
    for attempt in range(1, max_retries + 1):
        if is_db_connected():
            print(f"[DB] PostgreSQL connection verified (attempt {attempt}).")
            return True
        print(f"[DB] Waiting for PostgreSQL to be ready (attempt {attempt}/{max_retries})...")
        time.sleep(delay)
    return False

def run_migration_if_needed():
    if not wait_for_db(max_retries=15, delay=2):
        print("[WARN] Database is not reachable right now. Skipping migration.")
        return False

    # Step 1: ALWAYS ensure all foundational tables & schemas exist first (0.1s execution)
    print("[INFO] Step 1: Ensuring all database schemas, tables, and credentials...")
    try:
        init_system_db.setup_all_schemas()
        print("[SUCCESS] All schemas (appointments, patients, doctors, notifications) verified!")
    except Exception as e:
        print(f"[ERROR] Error configuring schemas: {e}")

    # Step 2: Check if doctors dataset needs to be seeded
    con = None
    needs_data_import = False
    try:
        con = get_connection()
        cur = con.cursor()
        try:
            cur.execute('SELECT COUNT(*) FROM "doctors";')
            cnt = cur.fetchone()[0]
            if cnt == 0:
                needs_data_import = True
            else:
                print(f"[INFO] Doctors catalogue active with {cnt:,} records.")
        except Exception as e:
            print(f"[INFO] Doctors check notice: {e}. Migration requested.")
            needs_data_import = True
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as exc:
        print(f"[WARN] Connection check notice: {exc}")
    finally:
        if con:
            try:
                con.close()
            except Exception:
                pass

    if needs_data_import:
        print("[INFO] Step 2: Fresh database detected. Importing initial doctor & hospital datasets...")
        try:
            import migrate_to_postgres
            migrate_to_postgres.run_all_migrations()
            print("[INFO] Dataset migration completed successfully!")
        except Exception as e:
            print(f"[WARN] Error during dataset migration: {e}")
    else:
        print("[INFO] Step 2: Database already contains doctors dataset. Preserving data.")

    return True

if __name__ == "__main__":
    success = run_migration_if_needed()
    if not success:
        print("[WARN] init_cloud_db completed with warnings.")
    sys.exit(0)
