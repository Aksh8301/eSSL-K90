import json
from zk import ZK

with open("config.json", "r", encoding="utf-8") as f:
    c = json.load(f)

# Only one device is connected at a time,
# so try each configured IP until one answers.
ips = c.get("device_ips") or [c.get("device_ip", "")]
ips = [str(ip).strip() for ip in ips if str(ip).strip()]

print("Connecting to K90...")
print("IPs:", ", ".join(ips), "Port:", c["device_port"])

conn = None
active_ip = None
last_error = None

for ip in ips:
    print("Trying", ip, "...")
    z = ZK(
        ip,
        port=int(c["device_port"]),
        timeout=10,
        password=int(c.get("comm_key", 0)),
        force_udp=False,
        ommit_ping=False
    )
    try:
        conn = z.connect()
        active_ip = ip
        break
    except Exception as error:
        last_error = error
        print("No response from", ip, "-", error)

if conn is None:
    print("FAILED: Could not connect to any K90.")
    print("Tried:", ", ".join(ips))
    print("Last error:", last_error)
else:
    names = c.get("device_names") or {}
    print("SUCCESS: Connected to K90 at", active_ip,
          "| Name:", names.get(active_ip, c.get("device_name", "K90")))
    try:
        print("Device:", conn.get_device_name())
    except Exception:
        pass
    conn.disconnect()
