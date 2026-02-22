from dotenv import load_dotenv
import os
import psycopg

load_dotenv()

conn = psycopg.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("""
select table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;
""")

for r in cur.fetchall():
    print(r[0])

conn.close()