import json
from datetime import date, datetime
from pathlib import Path
from db import get_connection

def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)

con = get_connection()
cur = con.cursor()

tables = ["patients", "appointments", "patient_reviews", "notifications", "hospitals", "faqs", "audit_logs"]
data_export = {}

for tbl in tables:
    try:
        cur.execute(f'SELECT * FROM "{tbl}";')
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        records = [dict(zip(cols, row)) for row in rows]
        data_export[tbl] = records
        print(f"Exported {tbl}: {len(records)} records")
    except Exception as e:
        print(f"Error exporting {tbl}: {e}")
        data_export[tbl] = []

con.close()

out_dir = Path("initial_data")
out_dir.mkdir(exist_ok=True)
out_file = out_dir / "localhost_history.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(data_export, f, default=json_serial, indent=2, ensure_ascii=False)

print(f"Successfully saved to {out_file} (size: {out_file.stat().st_size:,} bytes)")

