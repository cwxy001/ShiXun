import sys; sys.path.insert(0, '.')
from app.models.db import get_connection
c = get_connection()
rows = c.execute("PRAGMA table_info(digital_employees)").fetchall()
for r in rows:
    print(f"  {r['name']}  {r['type']}  default={r['dflt_value']}")
