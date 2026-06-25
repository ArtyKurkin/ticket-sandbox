<?php
// Простая форма и обработчик загрузки.
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!empty($_FILES['doc']) && $_FILES['doc']['error'] === UPLOAD_ERR_OK) {
        $size = $_FILES['doc']['size'];
        echo "OK: получен файл размером " . $size . " байт";
    } else {
        $code = isset($_FILES['doc']) ? $_FILES['doc']['error'] : 'no file';
        http_response_code(400);
        echo "ERROR: файл не принят (code " . $code . ")";
    }
    exit;
}
?>
<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Загрузка документа</title></head>
<body>
  <h1>Загрузка документа</h1>
  <form method="post" enctype="multipart/form-data">
    <input type="file" name="doc">
    <button type="submit">Загрузить</button>
  </form>
</body></html>
