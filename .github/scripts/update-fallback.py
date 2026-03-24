#!/usr/bin/env python3
"""
Updates the hardcoded NEWS_FALLBACK in index.html with the latest AI-generated news.
Run after generate-news.py to keep fallback fresh.
"""

import json
import os
import re

# Needed by news_to_js

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(SCRIPT_DIR, '..', '..')
NEWS_PATH = os.path.join(ROOT, 'data', 'news-latest.json')
HTML_PATH = os.path.join(ROOT, 'index.html')


def news_to_js(news_items):
    """Convert news array to JS source code using JSON.parse (safe escaping)."""
    # Use JSON.stringify which is always valid JS
    clean_items = []
    for item in news_items:
        clean_items.append({
            'category': item.get('category', 'NEWS'),
            'headline': item.get('headline', ''),
            'summary': item.get('summary', ''),
            'source': item.get('source', ''),
            'link': item.get('link', ''),
            'image': item.get('image'),
            'dataBoxes': item.get('dataBoxes')
        })
    # Clean newlines from string values (they break JSON.parse in template literals)
    def clean_val(v):
        if isinstance(v, str):
            return v.replace('\n', ' ').replace('\r', ' ').strip()
        if isinstance(v, dict):
            return {k: clean_val(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [clean_val(vv) for vv in v]
        return v

    clean_items = [clean_val(item) for item in clean_items]
    json_str = json.dumps(clean_items, ensure_ascii=True)
    # Escape backticks and ${} for JS template literal safety
    json_str = json_str.replace('`', '\\`').replace('${', '\\${')
    return f'JSON.parse(`{json_str}`)'


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

    # Find and replace the NEWS_FALLBACK array using string search (avoid regex escaping issues)
    start_marker = 'const NEWS_FALLBACK = '
    start_idx = html.find(start_marker)
    if start_idx == -1:
        print('Could not find NEWS_FALLBACK in index.html')
        return

    # Find the closing semicolon after JSON.parse(`...`); or [...];
    search_from = start_idx + len(start_marker)
    # Find the next line that starts with "    let NEWS" (the line after the fallback)
    end_marker = '\n\n    let NEWS'
    end_idx = html.find(end_marker, search_from)
    if end_idx == -1:
        print('Could not find end of NEWS_FALLBACK')
        return

    new_fallback = f'{start_marker}{news_to_js(news)};'
    new_html = html[:start_idx] + new_fallback + html[end_idx:]
    count = 1

    with open(HTML_PATH, 'w') as f:
        f.write(new_html)

    print(f'Updated NEWS_FALLBACK with {len(news)} items')


if __name__ == '__main__':
    main()
