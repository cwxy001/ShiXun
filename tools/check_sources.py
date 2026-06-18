import sys; sys.path.insert(0, '.')
from app.models.db import get_connection
c = get_connection()
rows = c.execute("SELECT * FROM watch_sources").fetchall()
print(f"数据源总数: {len(rows)}")
for r in rows:
    d = dict(r)
    print(f"  [{d['id']}] {d['name']}")
    print(f"       URL模板: {d['url_template']}")
    print(f"       方法: {d['method']}  分页: {d['enable_pagination']}")
    print(f"       状态: {d.get('status', 'enabled')}")
    print()
