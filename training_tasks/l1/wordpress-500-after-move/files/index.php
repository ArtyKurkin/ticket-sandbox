<?php
// Учебное приложение. Ведёт себя как CMS после переноса.
// Читает доступы к БД из wp-config.php (как настоящий WP).

error_reporting(E_ALL);
ini_set('log_errors', '1');

$configFile = '/var/www/html/wp-config.php';
if (!file_exists($configFile)) {
    http_response_code(500);
    error_log("FATAL: wp-config.php not found");
    exit;
}
require $configFile;

// CMS использует mbstring для обработки текста.
// Если модуль не установлен — fatal error, как в реальном WP.
if (!function_exists('mb_strlen')) {
    http_response_code(500);
    error_log("PHP Fatal error: Call to undefined function mb_strlen() - mbstring extension missing");
    exit;
}

// Подключение к БД с доступами из конфига.
$mysqli = @mysqli_connect(DB_HOST, DB_USER, DB_PASSWORD, DB_NAME);
if (!$mysqli) {
    http_response_code(500);
    error_log("WordPress database error: " . mysqli_connect_error() . " (Access denied / wrong credentials)");
    exit;
}

$title = mb_strlen("Сайт") > 0 ? "Сайт клиента" : "Сайт";
echo "<h1>" . $title . " работает</h1>";
echo "<p>Соединение с базой данных установлено.</p>";
$mysqli->close();
