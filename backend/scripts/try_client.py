from app import config
from app.portal_client import PortalClient

c = PortalClient(config.BASE_URL, config.EMAIL, config.PASSWORD)

exp = c.fetch_export(1)
print("export total:", exp.get("total"), "records:", len(exp["data"]))

rows = c.fetch_energy("J100008")
print("energy rows:", len(rows), rows[0]["timestamp"], rows[-1]["timestamp"])

try:
    p2 = c.fetch_export(2)
    print("export page 2:", p2.get("total"), len(p2.get("data", [])))
except Exception as exc:
    print("export page 2 failed:", exc)