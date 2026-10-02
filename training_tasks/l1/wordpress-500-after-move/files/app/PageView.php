<?php
final class PageView
{
    private string $siteName;

    public function __construct(string $siteName)
    {
        $this->siteName = mb_strimwidth($siteName, 0, 80, '…', 'UTF-8');
    }

    public function render(string $content): void
    {
        echo '<h1>' . htmlspecialchars($this->siteName, ENT_QUOTES, 'UTF-8') . '</h1>';
        echo '<p>' . htmlspecialchars($content, ENT_QUOTES, 'UTF-8') . '</p>';
    }
}
