<?php
// Platform-owned checker. This file is never copied into a trainee task image.
// No diagnostic PHP files or credentials are written into the web root.

function fcgiRecord(int $type, string $data): string
{
    return pack('CCnnCC', 1, $type, 1, strlen($data), 0, 0) . $data;
}

function fcgiLength(int $length): string
{
    return $length < 128 ? chr($length) : pack('N', $length | 0x80000000);
}

function readExact($socket, int $length): string
{
    $result = '';
    while (strlen($result) < $length) {
        $part = fread($socket, $length - strlen($result));
        if ($part === false || $part === '') {
            throw new RuntimeException('Incomplete runtime response');
        }
        $result .= $part;
    }
    return $result;
}

function runtimeProbe(): array
{
    // Inspect the configured upstream, rather than assuming a PHP version/socket.
    exec('nginx -T 2>/dev/null', $configuration, $status);
    if ($status !== 0 || !preg_match('/fastcgi_pass\s+([^;\s]+)\s*;/', implode("\n", $configuration), $match)) {
        throw new RuntimeException('No application runtime');
    }
    $upstream = $match[1];
    $address = str_starts_with($upstream, 'unix:')
        ? 'unix://' . substr($upstream, 5) : 'tcp://' . $upstream;
    $socket = stream_socket_client($address, $errno, $error, 3);
    if ($socket === false) {
        throw new RuntimeException('Runtime unavailable');
    }
    stream_set_timeout($socket, 5);
    // Execute in the actual FPM worker with its loaded extensions and app config.
    // FastCGI stdin supplies the prepend source; it never becomes a task file.
    $source = <<<'PROBE'
<?php
try {
    if (!extension_loaded('mbstring') || mb_strlen('Сайт', 'UTF-8') !== 4) {
        throw new RuntimeException('Runtime dependency unavailable');
    }
    require '/var/www/html/wp-config.php';
    mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
    $db = new mysqli(DB_HOST, DB_USER, DB_PASSWORD, DB_NAME);
    $db->set_charset('utf8mb4');
    $page = $db->query("SELECT content FROM site_pages WHERE slug = 'home'")->fetch_assoc();
    $server = $db->query('SELECT @@server_uuid AS id')->fetch_assoc();
    if (!$page) { throw new RuntimeException('No home page'); }
    header('Content-Type: application/json');
    echo json_encode(['content' => $page['content'], 'database' => DB_NAME, 'server' => $server['id']], JSON_THROW_ON_ERROR);
} catch (Throwable $error) {
    http_response_code(500);
    echo '{}';
}
exit;
PROBE;
    $params = [
        'GATEWAY_INTERFACE' => 'CGI/1.1',
        'REQUEST_METHOD' => 'POST',
        'SCRIPT_FILENAME' => '/var/www/html/index.php',
        'SCRIPT_NAME' => '/index.php',
        'REQUEST_URI' => '/index.php',
        'SERVER_NAME' => 'localhost',
        'SERVER_PORT' => '80',
        'SERVER_PROTOCOL' => 'HTTP/1.1',
        'CONTENT_TYPE' => 'application/octet-stream',
        'CONTENT_LENGTH' => (string) strlen($source),
        'PHP_ADMIN_VALUE' => "allow_url_include=1\nauto_prepend_file=php://input\ndisplay_errors=0\nlog_errors=0",
    ];
    $encoded = '';
    foreach ($params as $name => $value) {
        $encoded .= fcgiLength(strlen($name)) . fcgiLength(strlen($value)) . $name . $value;
    }
    $request = fcgiRecord(1, pack('nCxxxxx', 1, 0))
        . fcgiRecord(4, $encoded) . fcgiRecord(4, '')
        . fcgiRecord(5, $source) . fcgiRecord(5, '');
    while ($request !== '') {
        $written = fwrite($socket, $request);
        if ($written === false || $written === 0) {
            throw new RuntimeException('Runtime write failed');
        }
        $request = substr($request, $written);
    }
    $output = '';
    while (true) {
        $header = unpack('Cversion/Ctype/nid/nlength/Cpadding/Creserved', readExact($socket, 8));
        $body = readExact($socket, $header['length']);
        readExact($socket, $header['padding']);
        if ($header['type'] === 6) { $output .= $body; }
        if ($header['type'] === 3) { break; }
    }
    fclose($socket);
    $parts = explode("\r\n\r\n", $output, 2);
    $result = json_decode($parts[1] ?? '', true, 512, JSON_THROW_ON_ERROR);
    if (!isset($result['content'], $result['database'], $result['server'])) {
        throw new RuntimeException('Application dependencies unavailable');
    }
    return $result;
}

function pageContains(string $content): bool
{
    $url = 'http://127.0.0.1/index.php?check=' . bin2hex(random_bytes(12));
    // -f requires successful HTTP status; proxy settings cannot mask local errors.
    exec('curl --noproxy ' . escapeshellarg('*') . ' -fsS --max-time 5 '
        . escapeshellarg($url) . ' -w ' . escapeshellarg("\n%{http_code}") . ' 2>/dev/null', $lines, $status);
    $httpStatus = array_pop($lines);
    return $status === 0 && $httpStatus === '200' && $content !== ''
        && str_contains(implode("\n", $lines), htmlspecialchars($content, ENT_QUOTES, 'UTF-8'));
}

$admin = null;
$original = null;
$challenge = null;
$passed = false;
try {
    $runtime = runtimeProbe();
    if (!pageContains($runtime['content'])) {
        throw new RuntimeException('Application response failed');
    }
    // Administer only this local fixture DB. App credentials are verified above
    // in FPM; the app may legitimately have SELECT-only rights.
    mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
    $admin = new mysqli('localhost', 'root', '', $runtime['database']);
    $admin->set_charset('utf8mb4');
    $server = $admin->query('SELECT @@server_uuid AS id')->fetch_assoc();
    if ($server['id'] !== $runtime['server']) {
        throw new RuntimeException('Unexpected database server');
    }
    $original = $admin->query("SELECT content FROM site_pages WHERE slug = 'home'")->fetch_assoc()['content'];
    $challenge = $original . ' [check-' . bin2hex(random_bytes(24)) . ']';
    // Restore even on HTTP failure or the outer timeout's SIGTERM. The compare
    // prevents overwriting an unrelated edit made during the check.
    register_shutdown_function(function () use (&$admin, &$original, &$challenge) {
        if ($admin !== null && $challenge !== null) {
            $restore = $admin->prepare("UPDATE site_pages SET content = ? WHERE slug = 'home' AND content = ?");
            $restore->bind_param('ss', $original, $challenge);
            $restore->execute();
        }
    });
    if (function_exists('pcntl_signal')) {
        pcntl_async_signals(true);
        pcntl_signal(SIGTERM, function () { exit(1); });
    }
    $update = $admin->prepare("UPDATE site_pages SET content = ? WHERE slug = 'home' AND content = ?");
    $update->bind_param('ss', $challenge, $original);
    $update->execute();
    if ($update->affected_rows !== 1 || !pageContains($challenge)) {
        throw new RuntimeException('Page is not reading current database data');
    }
    $restore = $admin->prepare("UPDATE site_pages SET content = ? WHERE slug = 'home' AND content = ?");
    $restore->bind_param('ss', $original, $challenge);
    $restore->execute();
    if ($restore->affected_rows !== 1) {
        throw new RuntimeException('Concurrent page update');
    }
    $challenge = null;
    $passed = pageContains($original);
} catch (Throwable $error) {
    // Do not print diagnostic source, credentials or a ready-made solution.
}
echo $passed
    ? "✅ Приложение работает и отображает актуальные данные.\nЗадание пройдено.\n"
    : "❌ Рабочее состояние приложения не подтверждено. Проверь HTTP и логи приложения.\n";
exit($passed ? 0 : 1);
