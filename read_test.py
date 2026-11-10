import json
from zk import ZK

with open("config.json", "r", encoding="utf-8") as f:
    c=json.load(f)

# Only one device is connected at a time,
# so try each configured IP until one answers.
ips = c.get("device_ips") or [c.get("device_ip", "")]
ips = [str(ip).strip() for ip in ips if str(ip).strip()]

conn=None
active_ip=None
last_error=None

for ip in ips:
    print("Connecting to K90 at", ip, "...")
    z=ZK(
        ip,
        port=int(c["device_port"]),
        timeout=10,
        password=int(c.get("comm_key",0)),
        force_udp=False,
        ommit_ping=False
    )
    try:
        conn=z.connect()
        active_ip=ip
        break
    except Exception as error:
        last_error=error
        print("No response from", ip, "-", error)

if conn is None:
    print("\nFAILED: Could not connect to any K90.")
    print("Tried:", ", ".join(ips))
    print("Last error:", last_error)
    input("\nPress Enter to close...")
    raise SystemExit(1)

try:
    names = c.get("device_names") or {}
    print("SUCCESS: Connected to K90 at", active_ip,
          "| Name:", names.get(active_ip, c.get("device_name", "K90")))
    print("\nReading attendance logs...\n")
    logs=conn.get_attendance()

    if not logs:
        print("No attendance records found on the K90.")
    else:
        print(f"Found {len(logs)} attendance records:\n")
        print("-"*75)
        print(f"{'User ID':<15}{'Date/Time':<25}{'Status':<10}{'Punch':<10}{'Verify':<10}")
        print("-"*75)

        for a in logs:
            print(
                f"{str(a.user_id):<15}"
                f"{str(a.timestamp):<25}"
                f"{str(getattr(a,'status','')):<10}"
                f"{str(getattr(a,'punch','')):<10}"
                f"{str(getattr(a,'verify','')):<10}"
            )

        print("-"*75)
        print("\nThese records were ONLY read. Nothing was uploaded or deleted.")
finally:
    if conn:
        conn.disconnect()

input("\nPress Enter to close...")
