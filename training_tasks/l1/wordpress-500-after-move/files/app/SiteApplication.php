<?php
final class SiteApplication
{
    public function renderHome(): void
    {
        $view = new PageView('Сайт клиента работает');
        mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
        $database = new mysqli(DB_HOST, DB_USER, DB_PASSWORD, DB_NAME);
        $database->set_charset('utf8mb4');
        $result = $database->query("SELECT content FROM site_pages WHERE slug = 'home'");
        $page = $result->fetch_assoc();
        if (!$page) {
            throw new RuntimeException('Home page not found');
        }
        $view->render($page['content']);
        $database->close();
    }
}
