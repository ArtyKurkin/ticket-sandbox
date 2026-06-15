<?php

mysqli_report(MYSQLI_REPORT_OFF);

$mysqli = @new mysqli(
    "localhost",
    "root",
    "",
    "site_db"
);

if ($mysqli->connect_errno) {
    http_response_code(500);

    echo "<h1>500 Internal Server Error</h1>";

    error_log(
        "MySQL connection failed: " .
        $mysqli->connect_error
    );

    exit;
}

$result = $mysqli->query("SELECT name FROM users");

if (!$result) {
    http_response_code(500);

    echo "<h1>500 Internal Server Error</h1>";

    error_log(
        "Database query error: " .
        $mysqli->error
    );

    exit;
}

echo "<h1>Site is working</h1>";

while ($row = $result->fetch_assoc()) {
    echo "<p>" . htmlspecialchars($row["name"]) . "</p>";
}