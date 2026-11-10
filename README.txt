eSSL K90 DIRECT SYNC

Flow:
K90 -> TCP/IP -> Windows sync program -> HTTPS -> PHP API -> MySQL

This bypasses eTimeTrackLite.

1. K90 (two units, only one connected at a time):
   IP: 192.168.1.201  or  192.168.1.200
   Subnet: 255.255.255.0
   Use the actual TCP COMM Port shown in the K90.
   Common port is 4370.
   Comm Key is commonly 0 unless changed.
   The sync program tries every IP in device_ips and
   connects to whichever device answers.

2. PC Ethernet:
   IP: 192.168.1.100
   Subnet: 255.255.255.0
   Gateway: blank
   DNS: blank

3. Install Python 3 and enable "Add Python to PATH".

4. Double-click install.bat.

5. Edit config.json:
   device_ips (list both IPs: 192.168.1.201 and 192.168.1.200)
   device_names (name for each IP:
     192.168.1.201 = Coaching
     192.168.1.200 = PRT)
   device_records (values sent to the API:
     Coaching -> device_id=DEV_DEP, serial_number=SN_DEP
     PRT      -> device_id=DEV_PRT, serial_number=SN_PRT)
   verification_mode (always Fingerprint)
   device_port
   comm_key
   api_url
   api_key
   interval_seconds

6. First run test_device.bat.
   It must say SUCCESS before running the sync.

7. Run run.bat.
   It reads K90 attendance every 60 seconds and sends new records to the PHP API.
   It does NOT delete logs from the K90.

8. After successful testing, use Windows Task Scheduler to run:
   python C:\eSSL-K90-Direct-Sync\k90_sync.py
   At system startup.

IMPORTANT:
This is a direct-protocol implementation using the common ZK/eSSL protocol. K90 firmware can vary.
If test_device.bat fails even though ping works, check the K90 TCP COMM Port and Comm Key first.
Do not expose the K90 TCP port to the public Internet.

The PHP API must accept:
employee_code
punch_time
direction
device_id
serial_number
verification_mode
device_name
