import sys; sys.path.insert(0, '.')
from app.models.db import get_connection
c = get_connection()
rows = c.execute("SELECT * FROM digital_employees").fetchall()
for r in rows:
    d = dict(r)
    print(f"[{d['id']}] {d['name']}")
    print(f"  role_name={d['role_name']}")
    print(f"  greeting={d['greeting']}")
    print(f"  system_prompt={d['system_prompt']}")
    print(f"  skills={d['skills']}")
    print(f"  model_engine_id={d['model_engine_id']}")
    print()
