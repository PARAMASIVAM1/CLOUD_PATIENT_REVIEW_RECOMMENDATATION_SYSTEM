"""
init_cloud_db.py - Automated Database Setup & Migration for Render Cloud Deployment

Can be run automatically in Render Build Command or manually from Render Web Shell.
If the database is fresh, it imports the dataset and creates all necessary tables.
If the database already has data, it safely ensures all schemas & admin accounts are ready.
"""

import os
import sys
import time
import pandas as pd
from db import get_connection, is_db_connected
import init_system_db

def run_migration_if_needed():
    if not is_db_connected():
        print("[WARN] Database is not reachable right now. Skipping migration.")
        return

    con = get_connection()
    cur = con.cursor()

    # Check if doctors table exists and has rows
    needs_data_import = False
    try:
        cur.execute("SELECT COUNT(*) FROM \"doctors\";")
        cnt = cur.fetchone()[0]
        if cnt == 0:
            needs_data_import = True
    except Exception:
        needs_data_import = True

    con.close()

    if needs_data_import:
        print("[INFO] Fresh cloud database detected. Migrating initial dataset...")
        try:
            import migrate_to_postgres
            print("[INFO] Initial dataset migration completed!")
        except Exception as e:
            print(f"[WARN] Error during dataset migration: {e}")
    else:
        print("[INFO] Database already contains doctor records. Preserving existing data.")

    # Always ensure schemas and default admin account exist
    print("[INFO] Ensuring all schemas, tables, and admin credentials...")
    try:
        init_system_db.setup_all_schemas()
        print("[SUCCESS] Cloud database is fully initialized and ready for production!")
    except Exception as e:
        print(f"[ERROR] Error configuring schemas: {e}")

if __name__ == "__main__":
    run_migration_if_needed()

