#!/usr/bin/env python3
"""
Updates the hardcoded NEWS_FALLBACK in index.html with the latest AI-generated news.
Run after generate-news.py to keep fallback fresh.
"""

import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(SCRIPT_DIR, '..', '..')
NEWS_PATH = os.path.join(ROOT, 'data', 'news-latest.json')
HTML_PATH = os.path.join(ROOT, 'index.html')


def js_value(val):
    """Convert Python value to JS literal string."""
    if val is None:
        return 'null'
    if isinstance(val, bool):
        return 'true' if val else 'false'
    if isinstance(val, str):
        escaped = val.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
        return f"'{escaped}'"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, dict):
        items = ', '.join(f'{k}: {js_value(v)}' for k, v in val.items())
        return '{ ' + items + ' }'
    if isinstance(val, list):
        items = ',\n          '.join(js_value(v) for v in val)
        return '[\n          ' + items + '\n        ]'
    return str(val)


def news_to_js(news_items):
    """Convert news array to JS source code."""
    cards = []
    for item in news_items:
        parts = []
        parts.append(f"        category: {js_value(item.get('category', 'NEWS'))}")
        parts.append(f"        headline: {js_value(item.get('headline', ''))}")
        parts.append(f"        summary: {js_value(item.get('summary', ''))}")
        parts.append(f"        source: {js_value(item.get('source', ''))}")
        parts.append(f"        link: {js_value(item.get('link', ''))}")
        parts.append(f"        image: {js_value(item.get('image'))}")
        parts.append(f"        dataBoxes: {js_value(item.get('dataBoxes'))}")
        cards.append('      {\n' + ',\n'.join(parts) + '\n      }')
    return '[\n' + ',\n'.join(cards) + '\n    ]'


def main():
    if not os.path.exists(NEWS_PATH):
        print('No news-latest.json found, skipping fallback update')
        return

    with open(NEWS_PATH) as f:
        data = json.load(f)

    news = data.get('news', [])
    if not news:
        print('No news items, skipping')
        return

    with open(HTML_PATH) as f:
        html = f.read()

    # Find and replace the NEWS_FALLBACK array
    pattern = r'(const NEWS_FALLBACK = )\[[\s\S]*?\n    \];'
    replacement = f'\\1{news_to_js(news)};'

    new_html, count = re.subn(pattern, replacement, html, count=1)

    if count == 0:
        print('Could not find NEWS_FALLBACK in index.html')
        return

    with open(HTML_PATH, 'w') as f:
        f.write(new_html)

    print(f'Updated NEWS_FALLBACK with {len(news)} items')


if __name__ == '__main__':
    main()
