<?php

// =====================================================
// eSSL K90 ATTENDANCE API
// Receives one punch per POST from the Windows sync
// program (k90_sync.py) and stores it in the online
// MySQL table: attendance_logs
//
// Request:
//   POST with header X-API-Key
//   Body: JSON with employee_code, employee_name,
//         punch_time, direction, device_id,
//         serial_number, verification_mode, device_name
//
// Device mapping done by the PC sync program:
//   192.168.1.201 -> device_name=Coaching
//                    device_id=DEV_DEP  serial_number=SN_DEP
//   192.168.1.200 -> device_name=PRT
//                    device_id=DEV_PRT  serial_number=SN_PRT
//   verification_mode is always "Fingerprint"
//
// Response: JSON { "ok": true, ... } - the sync program
// only marks a punch as sent when ok === true.
// =====================================================

header('Content-Type: application/json');

// =====================================================
// SECURITY
// =====================================================

// CHANGE THIS to your own random secret.
// Use the SAME key in your PC's config.json.
$API_KEY = '9412418709';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode([
        'ok' => false,
        'error' => 'POST required'
    ]);
    exit;
}

$receivedKey = $_SERVER['HTTP_X_API_KEY'] ?? '';

if (!hash_equals($API_KEY, $receivedKey)) {
    http_response_code(401);
    echo json_encode([
        'ok' => false,
        'error' => 'Unauthorized'
    ]);
    exit;
}


// =====================================================
// READ JSON
// =====================================================

$input = json_decode(file_get_contents('php://input'), true);

if (!is_array($input)) {
    http_response_code(400);
    echo json_encode([
        'ok' => false,
        'error' => 'Invalid JSON'
    ]);
    exit;
}


// =====================================================
// HELPERS
// =====================================================

/**
 * Trim a value and cut it to the MySQL column size,
 * so a long value can never fail the INSERT.
 */
function clean_value($value, $maxLen)
{
    if ($value === null) {
        return null;
    }

    $value = trim((string)$value);

    if ($value === '') {
        return null;
    }

    if (function_exists('mb_substr')) {
        return mb_substr($value, 0, $maxLen, 'UTF-8');
    }

    return substr($value, 0, $maxLen);
}


// =====================================================
// ATTENDANCE DATA
// =====================================================

$employeeCode = clean_value($input['employee_code'] ?? null, 50);
$employeeName = clean_value($input['employee_name'] ?? null, 100);
$direction     = clean_value($input['direction'] ?? null, 10);
$deviceId      = clean_value($input['device_id'] ?? null, 100);
$serialNumber  = clean_value($input['serial_number'] ?? null, 100);
$verificationMode = clean_value($input['verification_mode'] ?? null, 50);
$deviceName    = clean_value($input['device_name'] ?? null, 100);

$punchTimeRaw = trim((string)($input['punch_time'] ?? ''));

if ($employeeCode === null || $punchTimeRaw === '') {
    http_response_code(400);

    echo json_encode([
        'ok' => false,
        'error' => 'employee_code and punch_time are required'
    ]);

    exit;
}

// Normalize punch_time to MySQL datetime (YYYY-MM-DD HH:MM:SS)
$dt = DateTime::createFromFormat('Y-m-d H:i:s', $punchTimeRaw);

if ($dt === false) {
    try {
        $dt = new DateTime($punchTimeRaw);
    } catch (Exception $e) {
        $dt = false;
    }
}

if ($dt === false) {
    http_response_code(400);

    echo json_encode([
        'ok' => false,
        'error' => 'Invalid punch_time, expected YYYY-MM-DD HH:MM:SS'
    ]);

    exit;
}

$punchTime = $dt->format('Y-m-d H:i:s');


// =====================================================
// DATABASE
// =====================================================

$dbHost = 'localhost';
$dbName = 'mccbeatleanalyti_db';
$dbUser = 'mccbeatleanalyti_user';
$dbPass = 'Cee;[+&e$a+9rAXe';


try {

    $pdo = new PDO(
        "mysql:host=$dbHost;dbname=$dbName;charset=utf8mb4",
        $dbUser,
        $dbPass,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
        ]
    );


    // =================================================
    // SKIP IF ALREADY STORED
    // The sync program may retry after a timeout, so
    // the same punch must never be inserted twice.
    // =================================================

    $check = $pdo->prepare("
        SELECT id
        FROM attendance_logs
        WHERE employee_code = :employee_code
          AND punch_time = :punch_time
          AND (device_id <=> :device_id)
        LIMIT 1
    ");

    $check->execute([
        ':employee_code' => $employeeCode,
        ':punch_time' => $punchTime,
        ':device_id' => $deviceId
    ]);

    $existingId = $check->fetchColumn();

    if ($existingId !== false) {
        echo json_encode([
            'ok' => true,
            'duplicate' => true,
            'id' => (int)$existingId
        ]);
        exit;
    }


    // =================================================
    // INSERT ATTENDANCE
    // =================================================

    $sql = "
        INSERT INTO attendance_logs
        (
            employee_code,
            employee_name,
            punch_time,
            direction,
            device_id,
            serial_number,
            verification_mode,
            device_name
        )
        VALUES
        (
            :employee_code,
            :employee_name,
            :punch_time,
            :direction,
            :device_id,
            :serial_number,
            :verification_mode,
            :device_name
        )
    ";


    $stmt = $pdo->prepare($sql);

    try {

        $stmt->execute([
            ':employee_code' => $employeeCode,
            ':employee_name' => $employeeName,
            ':punch_time' => $punchTime,
            ':direction' => $direction,
            ':device_id' => $deviceId,
            ':serial_number' => $serialNumber,
            ':verification_mode' => $verificationMode,
            ':device_name' => $deviceName
        ]);

        echo json_encode([
            'ok' => true,
            'duplicate' => false,
            'id' => (int)$pdo->lastInsertId()
        ]);

    } catch (PDOException $insertError) {

        // 23000 = unique constraint violated (same punch
        // inserted between our check and this insert)
        if ($insertError->getCode() === '23000') {
            echo json_encode([
                'ok' => true,
                'duplicate' => true
            ]);
            exit;
        }

        throw $insertError;
    }


} catch (Throwable $e) {

    http_response_code(500);

    echo json_encode([
        'ok' => false,
        'error' => 'Database error'
    ]);
}
?>