import json
import os
from openpyxl import load_workbook
from zk import ZK

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.json")
EXCEL_FILE = os.path.join(BASE, "employees.xlsx")


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_first_device_ip(config):
    ips = config.get("device_ips")
    if ips:
        return str(ips[0]).strip()

    ip = str(config.get("device_ip", "")).strip()
    if ip:
        return ip

    raise RuntimeError("No device_ip/device_ips found in config.json")


def load_employees():
    if not os.path.exists(EXCEL_FILE):
        raise FileNotFoundError(
            "employees.xlsx was not found: " + EXCEL_FILE
        )

    workbook = load_workbook(EXCEL_FILE, data_only=True)
    sheet = workbook.active
    employees = []

    # Excel format:
    # Column A = User ID
    # Column B = Name
    for row_number, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True), start=2
    ):
        user_id = row[0] if len(row) > 0 else None
        name = row[1] if len(row) > 1 else None

        if user_id is None and name is None:
            continue

        if user_id is None or name is None:
            print(f"SKIP row {row_number}: User ID or Name missing")
            continue

        user_id = str(user_id).strip()
        name = str(name).strip()

        if not user_id or not name:
            print(f"SKIP row {row_number}: User ID or Name missing")
            continue

        employees.append((user_id, name))

    return employees


def connect_k90(config, ip):
    zk = ZK(
        ip,
        port=int(config["device_port"]),
        timeout=10,
        password=int(config.get("comm_key", 0)),
        force_udp=False,
        ommit_ping=False
    )
    return zk.connect()


def import_employees(conn, ip, employees):
    users = conn.get_users()

    # Existing K90 User IDs, compared as strings.
    existing_ids = {
        str(user.user_id).strip()
        for user in users
        if getattr(user, "user_id", None) is not None
    }

    print("--------------------------------------")
    print("K90:", ip)
    print("Users currently on K90:", len(users))
    print("Employees in Excel:", len(employees))
    print("--------------------------------------")

    added = 0
    skipped = 0
    failed = 0

    conn.disable_device()

    try:
        for user_id, name in employees:

            if user_id in existing_ids:
                print(f"SKIP - Already on K90: {user_id} | {name}")
                skipped += 1
                continue

            try:
                # IMPORTANT:
                # Use the User ID directly from Excel.
                # Do NOT generate 1, 2, 3...
                conn.set_user(
                    uid=0,
                    user_id=user_id,
                    name=name,
                    privilege=0,
                    password="",
                    group_id="",
                    card=0
                )

                existing_ids.add(user_id)

                print(f"ADDED - {user_id} | {name}")
                added += 1

            except Exception as error:
                print(f"FAILED - {user_id} | {name} | {error}")
                failed += 1

    finally:
        conn.enable_device()

    print("--------------------------------------")
    print("IMPORT SUMMARY")
    print("--------------------------------------")
    print("Excel employees :", len(employees))
    print("Added           :", added)
    print("Skipped         :", skipped)
    print("Failed          :", failed)
    print("--------------------------------------")


def main():
    print("======================================")
    print(" eSSL K90 Excel Employee Import")
    print("======================================")

    conn = None

    try:
        config = load_config()
        ip = get_first_device_ip(config)
        employees = load_employees()

        if not employees:
            print("No employees found in employees.xlsx")
            input("Press Enter to close...")
            return

        print("Excel:", EXCEL_FILE)
        print("K90:", ip)
        print()

        conn = connect_k90(config, ip)
        print("CONNECTED:", ip)

        import_employees(conn, ip, employees)

        print()
        print("Employee import finished.")

    except Exception as error:
        print("ERROR:", error)

    finally:
        if conn:
            try:
                conn.enable_device()
            except Exception:
                pass

            try:
                conn.disconnect()
            except Exception:
                pass

    input("Press Enter to close...")


if __name__ == "__main__":
    main()
