"""
init_cloud_db.py - Automated Database Setup & Migration for Render Cloud Deployment

Can be run automatically in Render Start Command or manually from Render Web Shell.
If the database is fresh, it imports the dataset and creates all necessary tables.
If the database already has data, it safely ensures all schemas & admin accounts are ready.
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

    con = None
    needs_data_import = False
    try:
        con = get_connection()
        cur = con.cursor()

        # Check if doctors table exists and has rows
        try:
            cur.execute('SELECT COUNT(*) FROM "doctors";')
            cnt = cur.fetchone()[0]
            if cnt == 0:
                needs_data_import = True
            else:
                print(f"[INFO] Doctors table found with {cnt:,} records.")
        except Exception as e:
            print(f"[INFO] Doctors table not present yet ({e}). Will run initial dataset migration.")
            needs_data_import = True
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as exc:
        print(f"[WARN] Connection check notice: {exc}")
        needs_data_import = True
    finally:
        if con:
            try:
                con.close()
            except Exception:
                pass

    if needs_data_import:
        print("[INFO] Fresh cloud database detected. Migrating initial dataset...")
        try:
            import migrate_to_postgres
            migrate_to_postgres.run_all_migrations()
            print("[INFO] Initial dataset migration completed successfully!")
        except Exception as e:
            print(f"[WARN] Error during dataset migration: {e}")
    else:
        print("[INFO] Database already contains doctor records. Preserving existing data.")

    # Always ensure schemas and default admin account exist
    print("[INFO] Ensuring all schemas, tables, and admin credentials...")
    try:
        init_system_db.setup_all_schemas()
        print("[SUCCESS] Cloud database is fully initialized and ready for production!")
        return True
    except Exception as e:
        print(f"[ERROR] Error configuring schemas: {e}")
        return False

if __name__ == "__main__":
    success = run_migration_if_needed()
    if not success:
        print("[WARN] init_cloud_db completed with warnings.")
    sys.exit(0)
