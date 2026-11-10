import json
import os
import sqlite3
import time
from datetime import datetime

import requests
from zk import ZK


BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE, "config.json")
STATE = os.path.join(BASE, "sync_state.db")


def load_config():
    with open(CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


def get_device_ips(config):
    # New style: "device_ips": ["192.168.1.201", "192.168.1.200"]
    # Old style: "device_ip": "192.168.1.201"
    ips = config.get("device_ips")

    if not ips:
        ips = [config.get("device_ip", "")]

    return [str(ip).strip() for ip in ips if str(ip).strip()]


def get_device_name(config, ip):
    # Per-IP display name, e.g.
    # 192.168.1.201 -> "Coaching"
    # 192.168.1.200 -> "PRT"
    names = config.get("device_names") or {}

    name = str(names.get(ip, "")).strip()

    if name:
        return name

    return config.get("device_name", "K90")


def get_record_fields(config, device_name):
    # DB columns sent to the API for this device:
    # Coaching -> DEV_DEP / SN_DEP
    # PRT      -> DEV_PRT / SN_PRT
    records_cfg = config.get("device_records") or {}
    entry = records_cfg.get(device_name) or {}

    device_id = str(entry.get("device_id", "")).strip()
    serial_number = str(entry.get("serial_number", "")).strip()

    return {
        "device_id": device_id or device_name,
        "serial_number": serial_number or None,
        "verification_mode": config.get(
            "verification_mode",
            "Fingerprint"
        )
    }


def connect_device(config):
    # Only one device is connected at a time,
    # so try each configured IP until one answers.
    device_ips = get_device_ips(config)

    if not device_ips:
        raise RuntimeError(
            "No device_ip or device_ips set in config.json."
        )

    print("======================================")
    print("Connecting to K90...")
    print("======================================")

    last_error = None

    for ip in device_ips:

        zk = ZK(
            ip,
            port=int(config["device_port"]),
            timeout=10,
            password=int(config.get("comm_key", 0)),
            force_udp=False,
            ommit_ping=False
        )

        try:

            conn = zk.connect()

            print("K90 connected:", ip)

            return ip, conn

        except Exception as error:

            last_error = error

            print("No response from", ip, "-", error)

    raise RuntimeError(
        "Could not connect to any K90 ("
        + ", ".join(device_ips)
        + "). Last error: "
        + str(last_error)
    )


def init_db():
    db = sqlite3.connect(STATE)

    db.execute("""
        CREATE TABLE IF NOT EXISTS sent_punches (
            fingerprint TEXT PRIMARY KEY,
            sent_at TEXT NOT NULL
        )
    """)

    db.commit()
    return db


def fingerprint(record):
    # Use the physical device IP (source_ip) so changing the
    # API-facing device_id (DEV_DEP / DEV_PRT) does not break
    # dedupe against fingerprints already stored in sync_state.db.
    return "|".join([
        str(record["employee_code"]),
        str(record["punch_time"]),
        str(record.get("source_ip", record.get("device_id"))),
        str(record.get("status")),
        str(record.get("verify"))
    ])


def get_employee_names(conn):
    users = conn.get_users()

    employee_names = {}

    for user in users:
        user_id = str(user.user_id)
        name = getattr(user, "name", "") or ""

        employee_names[user_id] = name.strip()

    return employee_names


def upload_record(config, record):
    headers = {
        "X-API-Key": config["api_key"],
        "Content-Type": "application/json"
    }

    payload = {
        "employee_code": record["employee_code"],
        "employee_name": record["employee_name"],
        "punch_time": record["punch_time"],
        "direction": record["direction"],
        "device_id": record["device_id"],
        "serial_number": record["serial_number"],
        "verification_mode": record["verification_mode"],
        "device_name": record["device_name"]
    }

    response = requests.post(
        config["api_url"],
        headers=headers,
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(result)

    return True


def sync_once(config, db):

    device_ip = None
    conn = None

    try:

        device_ip, conn = connect_device(config)

        device_name = get_device_name(config, device_ip)
        record_fields = get_record_fields(config, device_name)

        conn.disable_device()

        # ---------------------------------------------
        # READ EMPLOYEE NAMES
        # ---------------------------------------------

        employee_names = get_employee_names(conn)

        print(
            "Employees found:",
            len(employee_names)
        )

        # ---------------------------------------------
        # READ ATTENDANCE
        # ---------------------------------------------

        logs = conn.get_attendance()

        print(
            "Attendance records on K90:",
            len(logs)
        )

        if not logs:

            print("Nothing to upload.")

            return

        uploaded = 0
        already_synced = 0
        failed = 0

        all_safe = True

        # ---------------------------------------------
        # UPLOAD EACH RECORD
        # ---------------------------------------------

        for attendance in sorted(
            logs,
            key=lambda x: x.timestamp
        ):

            employee_code = str(
                attendance.user_id
            )

            employee_name = employee_names.get(
                employee_code,
                ""
            )

            if not employee_name:
                employee_name = "Unknown"

            record = {

                "employee_code":
                    employee_code,

                "employee_name":
                    employee_name,

                "punch_time":
                    attendance.timestamp.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),

                "direction":
                    str(getattr(
                        attendance,
                        "punch",
                        ""
                    )),

                "device_id":
                    record_fields["device_id"],

                "serial_number":
                    record_fields["serial_number"],

                "verification_mode":
                    record_fields["verification_mode"],

                "device_name":
                    device_name,

                # Physical IP of the device that answered.
                # Only used for local dedupe, never uploaded.
                "source_ip":
                    device_ip,

                "status":
                    getattr(
                        attendance,
                        "status",
                        ""
                    ),

                "verify":
                    getattr(
                        attendance,
                        "verify",
                        ""
                    )
            }

            key = fingerprint(record)

            # -----------------------------------------
            # CHECK LOCAL SYNC DATABASE
            # -----------------------------------------

            exists = db.execute(
                """
                SELECT 1
                FROM sent_punches
                WHERE fingerprint=?
                """,
                (key,)
            ).fetchone()

            if exists:

                already_synced += 1

                continue

            # -----------------------------------------
            # UPLOAD TO MCC
            # -----------------------------------------

            try:

                upload_record(
                    config,
                    record
                )

                db.execute(
                    """
                    INSERT OR IGNORE INTO sent_punches
                    VALUES (?, ?)
                    """,
                    (
                        key,
                        datetime.now().isoformat(
                            timespec="seconds"
                        )
                    )
                )

                db.commit()

                uploaded += 1

                print(
                    "UPLOAD OK:",
                    employee_code,
                    "|",
                    employee_name,
                    "|",
                    record["punch_time"]
                )

            except Exception as error:

                failed += 1
                all_safe = False

                print(
                    "UPLOAD FAILED:",
                    employee_code,
                    "|",
                    record["punch_time"]
                )

                print(
                    "ERROR:",
                    error
                )

        # ---------------------------------------------
        # SAFETY CHECK
        # ---------------------------------------------

        print()
        print("--------------------------------------")
        print("Upload summary")
        print("--------------------------------------")

        print(
            "Total K90 records :",
            len(logs)
        )

        print(
            "Uploaded           :",
            uploaded
        )

        print(
            "Already synced     :",
            already_synced
        )

        print(
            "Failed             :",
            failed
        )

        print()

        # ---------------------------------------------
        # ONLY CLEAR IF EVERYTHING IS SAFE
        # ---------------------------------------------

        if failed > 0:

            print(
                "K90 CLEAR: SKIPPED"
            )

            print(
                "Reason: one or more records failed."
            )

            all_safe = False

        if all_safe:

            print(
                "All records are safely uploaded."
            )

            print(
                "Clearing attendance records from K90..."
            )

            try:

                result = conn.clear_attendance()

                if result:

                    print(
                        "K90 CLEAR: SUCCESS"
                    )

                else:

                    print(
                        "K90 CLEAR: DEVICE DID NOT CONFIRM"
                    )

                    return

            except Exception as error:

                print(
                    "K90 CLEAR: FAILED"
                )

                print(
                    "ERROR:",
                    error
                )

                return

            # -----------------------------------------
            # VERIFY CLEAR
            # -----------------------------------------

            print(
                "Verifying K90 attendance memory..."
            )

            try:

                remaining = conn.get_attendance()

                print(
                    "K90 records remaining:",
                    len(remaining)
                )

                if len(remaining) == 0:

                    print(
                        "K90 CLEAR VERIFICATION: SUCCESS"
                    )

                else:

                    print(
                        "WARNING:",
                        len(remaining),
                        "records remain on K90."
                    )

            except Exception as error:

                print(
                    "Could not verify K90:",
                    error
                )

        print("--------------------------------------")

    finally:

        if conn:

            try:
                conn.enable_device()
            except Exception:
                pass

            conn.disconnect()


def main():

    config = load_config()

    if (
        "YOURDOMAIN.com"
        in config["api_url"]
        or config["api_key"].startswith("PUT_")
    ):

        print(
            "Edit config.json first."
        )

        input(
            "Press Enter..."
        )

        return

    db = init_db()

    print()
    print(
        "======================================"
    )
    print(
        " eSSL K90 Direct Attendance Sync"
    )
    print(
        "======================================"
    )

    print(
        "K90:",
        ", ".join(get_device_ips(config)),
        ":",
        config["device_port"]
    )

    print(
        "API:",
        config["api_url"]
    )

    print(
        "Interval:",
        config["interval_seconds"],
        "seconds"
    )

    print()

    while True:

        try:

            sync_once(
                config,
                db
            )

        except KeyboardInterrupt:

            print(
                "\nSync stopped."
            )

            break

        except Exception as error:

            print(
                "SYNC ERROR:",
                error
            )

        print()
        print(
            "Next check in",
            config["interval_seconds"],
            "seconds..."
        )

        time.sleep(
            int(
                config["interval_seconds"]
            )
        )


if __name__ == "__main__":

    main()