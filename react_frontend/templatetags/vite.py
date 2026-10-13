import json
from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import ImproperlyConfigured
from django.utils.html import format_html, format_html_join

register = template.Library()


@register.simple_tag
def vite_assets(entry="src/main.tsx"):
    # Read through storage in production, so only the collected artifact is used.
    try:
        if settings.DEBUG:
            manifest = json.loads((settings.BASE_DIR / "static/frontend/manifest.json").read_text())
        else:
            with staticfiles_storage.open("frontend/manifest.json") as source:
                manifest = json.load(source)
        root = manifest[entry]
        css, imports, visited = [], [], set()

        def asset_url(path):
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("Invalid Vite asset path")
            return staticfiles_storage.url("frontend/" + path)

        def visit(key):
            if key in visited:
                return
            visited.add(key)
            chunk = manifest[key]
            for path in chunk.get("css", []):
                if path not in css:
                    css.append(path)
            for imported in chunk.get("imports", []):
                visit(imported)
                if manifest[imported]["file"] not in imports:
                    imports.append(manifest[imported]["file"])

        visit(entry)
        styles = format_html_join("\n", '<link rel="stylesheet" href="{}">', ((asset_url(p),) for p in css))
        preloads = format_html_join("\n", '<link rel="modulepreload" href="{}">', ((asset_url(p),) for p in imports))
        return format_html('{}\n{}\n<script type="module" src="{}"></script>', styles, preloads, asset_url(root["file"]))
    except (OSError, KeyError, ValueError) as exc:
        raise ImproperlyConfigured("React assets unavailable. Run npm ci and npm run build in frontend, then collectstatic in production.") from exc
