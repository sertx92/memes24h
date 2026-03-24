#!/usr/bin/env python3
"""
MEMES 24H - AI News Generator
Fetches data from 6529 API and OpenSea, generates news via AI (OpenRouter),
and updates the news JSON for the HTML card.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

# === CONFIG ===
OPENROUTER_KEY = os.environ.get('OPENROUTER_KEY', '')
OPENSEA_KEY = os.environ.get('OPENSEA_KEY', '0763c7f2c4104d288f734c0f91602913')
AI_MODEL = 'google/gemma-3-27b-it:free'
GIST_ID = os.environ.get('GIST_ID', '1b84f8b762cd2f6640ed7086cc9b7c69')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')

# Load waves config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'waves-config.json')

# === API HELPERS ===
def fetch_json(url, headers=None):
    """Fetch JSON from URL with optional headers."""
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Fetch error {url[:60]}: {e}")
        return None


def fetch_6529_drops(wave_id, limit=20):
    """Fetch latest drops from a 6529 wave."""
    url = f'https://api.6529.io/api/drops?wave_id={wave_id}&limit={limit}'
    return fetch_json(url) or []


def fetch_6529_submissions(wave_id, pages=10):
    """Fetch ranked submissions from a 6529 wave."""
    all_ranked = []
    sn = 999999
    for _ in range(pages):
        url = f'https://api.6529.io/api/drops?wave_id={wave_id}&drop_type=PARTICIPATION&limit=20&serial_no_less_than={sn}'
        data = fetch_json(url)
        if not data:
            break
        for d in data:
            if d.get('rank') is not None and d['rank'] <= 20:
                all_ranked.append({
                    'rank': d['rank'],
                    'title': d.get('title', 'Untitled'),
                    'author': d['author']['handle'],
                    'tdh': d.get('realtime_rating', 0),
                    'voters': d.get('raters_count', 0),
                    'img': d['parts'][0]['media'][0]['url'] if d['parts'][0].get('media') else None,
                    'drop_id': d['id']
                })
        sn = data[-1]['serial_no']
        if len(all_ranked) >= 10:
            break
    all_ranked.sort(key=lambda x: x['rank'])
    # Deduplicate by title
    seen = set()
    unique = []
    for d in all_ranked:
        if d['title'] not in seen:
            seen.add(d['title'])
            unique.append(d)
    return unique


def fetch_opensea_stats(slug):
    """Fetch collection stats from OpenSea."""
    url = f'https://api.opensea.io/api/v2/collections/{slug}/stats'
    return fetch_json(url, {'X-API-KEY': OPENSEA_KEY})


def fetch_opensea_sales(slug, limit=20):
    """Fetch recent sales from OpenSea."""
    url = f'https://api.opensea.io/api/v2/events/collection/{slug}?event_type=sale&limit={limit}'
    return fetch_json(url, {'X-API-KEY': OPENSEA_KEY})


# === DATA GATHERING ===
def gather_wave_data(waves):
    """Gather chat activity from waves."""
    wave_data = []
    for w in waves:
        print(f"Fetching wave: {w['name']}")
        drops = fetch_6529_drops(w['id'], 20)
        if not drops:
            continue

        now = datetime.now(timezone.utc).timestamp() * 1000
        recent_1h = [d for d in drops if d['created_at'] > now - 3600000]

        messages = []
        for d in drops[:10]:
            parts = d.get('parts', [])
            content = (parts[0].get('content') or '')[:200] if parts else ''
            author = d.get('author', {}).get('handle', '?')
            if content:
                messages.append(f"{author}: {content}")

        wave_data.append({
            'name': w['name'],
            'type': w.get('type', 'chat'),
            'message_count_1h': len(recent_1h),
            'total_messages': len(drops),
            'sample_messages': messages[:5],
            'wave_id': w['id']
        })
    return wave_data


def gather_submission_data(waves):
    """Gather submission/vote data from voting waves."""
    all_subs = []
    for w in waves:
        if w.get('type') != 'votes':
            continue
        print(f"Fetching submissions: {w['name']}")
        subs = fetch_6529_submissions(w['id'], pages=20)
        for s in subs:
            s['wave_name'] = w['name']
            s['wave_id'] = w['id']
        all_subs.extend(subs)
    return all_subs


def gather_market_data(collections):
    """Gather market data from OpenSea."""
    market = []
    for c in collections:
        print(f"Fetching market: {c['name']}")
        stats = fetch_opensea_stats(c['slug'])
        if not stats:
            continue

        sales_data = fetch_opensea_sales(c['slug'], 30)
        recent_sales = []
        whale_buyers = {}

        if sales_data and 'asset_events' in sales_data:
            for e in sales_data['asset_events']:
                price = int(e['payment']['quantity']) / 1e18
                buyer = e['buyer']
                name = e['nft']['name']
                recent_sales.append({'name': name, 'price': price, 'buyer': buyer[:10]})

                if buyer not in whale_buyers:
                    whale_buyers[buyer] = {'count': 0, 'spent': 0, 'last': ''}
                whale_buyers[buyer]['count'] += 1
                whale_buyers[buyer]['spent'] += price
                whale_buyers[buyer]['last'] = name

        # Find whales (3+ buys)
        whales = [
            {'address': addr[:8] + '...' + addr[-4:], **info}
            for addr, info in whale_buyers.items()
            if info['count'] >= 3
        ]
        whales.sort(key=lambda x: x['count'], reverse=True)

        market.append({
            'name': c['name'],
            'slug': c['slug'],
            'floor': stats['total'].get('floor_price', 0),
            'floor_symbol': stats['total'].get('floor_price_symbol', 'ETH'),
            'holders': stats['total'].get('num_owners', 0),
            'volume_24h': stats['intervals'][0].get('volume', 0) if stats.get('intervals') else 0,
            'sales_24h': stats['intervals'][0].get('sales', 0) if stats.get('intervals') else 0,
            'volume_7d': stats['intervals'][1].get('volume', 0) if stats.get('intervals') and len(stats['intervals']) > 1 else 0,
            'recent_sales': recent_sales[:5],
            'whales': whales[:2]
        })
    return market


# === AI NEWS GENERATION ===
def generate_news_with_ai(wave_data, submissions, market_data):
    """Send gathered data to AI and get news articles back."""
    if not OPENROUTER_KEY:
        print("No OpenRouter key, generating fallback news")
        return generate_fallback_news(wave_data, submissions, market_data)

    # Build the prompt
    prompt = f"""You are a news anchor for MEMES 24H, a daily broadcast covering the 6529 NFT ecosystem.
Today is {datetime.now(timezone.utc).strftime('%B %d, %Y')}.

Based on the following data, generate exactly 6-8 news items in JSON format.
Each news item must have: category, headline, summary, source, link (6529.io or opensea URL).
For submissions with images, include image_url and image_label.
For market news, include dataBoxes (array of {{label, value, sub}}).

Write headlines like a professional news anchor - concise, impactful, factual.
Highlight interesting patterns: whale activity, hot conversations, vote changes, notable sales.

=== WAVE ACTIVITY ===
{json.dumps(wave_data, indent=2)[:3000]}

=== TOP SUBMISSIONS (VOTES) ===
{json.dumps(submissions[:10], indent=2)[:3000]}

=== MARKET DATA ===
{json.dumps(market_data, indent=2)[:3000]}

Return ONLY a valid JSON array of news objects. No markdown, no explanation.
Format:
[
  {{
    "category": "MARKET|MAIN STAGE|COMMUNITY|WHALE ALERT|SUPERRARE x 6529|CULTURE",
    "headline": "Short punchy headline",
    "summary": "2-3 sentence summary with specific numbers and names",
    "source": "Source name",
    "link": "https://...",
    "image": {{"url": "...", "label": "..."}} or null,
    "dataBoxes": [{{"label": "...", "value": "...", "sub": "..."}}] or null
  }}
]"""

    body = json.dumps({
        'model': AI_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 3000,
        'temperature': 0.7
    }).encode()

    req = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=body,
        headers={
            'Authorization': f'Bearer {OPENROUTER_KEY}',
            'Content-Type': 'application/json'
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read())

        content = result['choices'][0]['message']['content']

        # Extract JSON from response (handle markdown code blocks)
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        news = json.loads(content.strip())
        print(f"AI generated {len(news)} news items")
        return news

    except Exception as e:
        print(f"AI generation failed: {e}")
        return generate_fallback_news(wave_data, submissions, market_data)


def generate_fallback_news(wave_data, submissions, market_data):
    """Generate news without AI (template-based fallback)."""
    news = []

    # Market news
    for m in market_data:
        if m['sales_24h'] > 0:
            top_sale = m['recent_sales'][0] if m['recent_sales'] else None
            headline = f"{m['name']}: {m['sales_24h']} Sales Today, Floor at {m['floor']} {m['floor_symbol']}"
            summary = f"24h volume: {m['volume_24h']:.2f} ETH across {m['sales_24h']} sales. {m['holders']:,} holders."
            if top_sale:
                summary += f' Latest sale: "{top_sale["name"]}" for {top_sale["price"]:.4f} ETH.'
            news.append({
                'category': 'MARKET',
                'headline': headline,
                'summary': summary,
                'source': 'OpenSea',
                'link': f"https://opensea.io/collection/{m['slug']}",
                'image': None,
                'dataBoxes': [
                    {'label': 'Floor', 'value': f"{m['floor']}", 'sub': m['floor_symbol']},
                    {'label': '24h Vol', 'value': f"{m['volume_24h']:.2f}", 'sub': 'ETH'},
                    {'label': 'Sales', 'value': str(m['sales_24h']), 'sub': 'Today'},
                    {'label': 'Holders', 'value': f"{m['holders']:,}", 'sub': ''}
                ]
            })

        # Whale alert
        for whale in m.get('whales', []):
            news.append({
                'category': 'WHALE ALERT',
                'headline': f"Whale {whale['address']} Buys {whale['count']} {m['name']}",
                'summary': f"Total spent: {whale['spent']:.3f} ETH. Last purchase: \"{whale['last']}\".",
                'source': 'OpenSea',
                'link': f"https://opensea.io/collection/{m['slug']}",
                'image': None,
                'dataBoxes': None
            })

    # Submission news
    if submissions:
        top3 = submissions[:3]
        news.append({
            'category': 'MAIN STAGE',
            'headline': f"#{top3[0]['rank']} {top3[0]['author']} Leads with {format_tdh(top3[0]['tdh'])} TDH",
            'summary': ' | '.join([f"#{s['rank']} \"{s['title']}\" by {s['author']} ({format_tdh(s['tdh'])} TDH, {s['voters']} voters)" for s in top3]),
            'source': top3[0].get('wave_name', 'Main Stage'),
            'link': f"https://6529.io/waves/{top3[0].get('wave_id', '')}",
            'image': {'url': top3[0]['img'], 'label': f"#{top3[0]['rank']} {top3[0]['title']}"} if top3[0].get('img') else None,
            'dataBoxes': [{'label': f"#{s['rank']} {s['author']}", 'value': format_tdh(s['tdh']), 'sub': f"TDH ({s['voters']} votes)"} for s in top3[:4]]
        })

    # Wave activity
    for w in wave_data:
        if w['message_count_1h'] > 0 and w['sample_messages']:
            msg = w['sample_messages'][0]
            news.append({
                'category': 'COMMUNITY',
                'headline': f"Active Discussion in {w['name']}",
                'summary': f"{w['message_count_1h']} messages in the last hour. Latest: {msg[:120]}",
                'source': w['name'],
                'link': f"https://6529.io/waves/{w['wave_id']}",
                'image': None,
                'dataBoxes': None
            })

    return news[:8]


def format_tdh(tdh):
    if tdh >= 1_000_000:
        return f"{tdh/1_000_000:.1f}M"
    if tdh >= 1_000:
        return f"{tdh/1_000:.0f}K"
    return str(tdh)


# === OUTPUT ===
def build_output(news, market_data):
    """Build the final JSON that the HTML card reads."""
    # Ticker data
    ticker = []
    for m in market_data:
        ticker.append({'label': f"{m['name']} Floor", 'value': f"{m['floor']} {m['floor_symbol']}"})
        if m['volume_24h'] > 0:
            ticker.append({'label': f"{m['name']} 24h", 'value': f"{m['volume_24h']:.2f} ETH"})

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'model': AI_MODEL,
        'news': news,
        'ticker': ticker
    }


def update_gist(output):
    """Update the GitHub Gist with new news data."""
    if not GITHUB_TOKEN or not GIST_ID:
        # Write to local file instead
        output_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'news-latest.json')
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"Written to {output_path}")
        return

    body = json.dumps({
        'files': {
            'news-latest.json': {
                'content': json.dumps(output, indent=2)
            }
        }
    }).encode()

    req = urllib.request.Request(
        f'https://api.github.com/gists/{GIST_ID}',
        data=body,
        method='PATCH',
        headers={
            'Authorization': f'Bearer {GITHUB_TOKEN}',
            'Content-Type': 'application/json'
        }
    )

    try:
        with urllib.request.urlopen(req) as r:
            result = json.loads(r.read())
        print(f"Gist updated: {result.get('html_url', 'OK')}")
    except Exception as e:
        print(f"Gist update failed: {e}")
        # Fallback to local file
        output_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'news-latest.json')
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"Written to {output_path}")


# === MAIN ===
def main():
    print(f"=== MEMES 24H News Generator ===")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    # Load config
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    else:
        print("No waves-config.json found, using defaults")
        config = {
            'waves': [
                {'id': 'b38288e6-ca9d-45ce-8323-3dc5e094f04e', 'name': "maybe's dive bar", 'type': 'chat'},
                {'id': 'b6128077-ea78-4dd9-b381-52c4eadb2077', 'name': 'The Memes - Main Stage', 'type': 'votes'},
                {'id': 'd22e3046-a00e-48b9-b245-a339a44c37cd', 'name': 'SuperRare Chat & Application Boost', 'type': 'votes'},
            ],
            'collections': [
                {'slug': 'thememes6529', 'name': 'The Memes'},
                {'slug': 'pebbles-by-zeblocks', 'name': 'Pebbles'},
            ]
        }

    # Gather data
    print("\n--- Gathering data ---")
    wave_data = gather_wave_data(config['waves'])
    submissions = gather_submission_data(config['waves'])
    market_data = gather_market_data(config['collections'])

    # Generate news
    print("\n--- Generating news ---")
    news = generate_news_with_ai(wave_data, submissions, market_data)

    # Build output
    output = build_output(news, market_data)
    print(f"\n--- Output: {len(news)} news items ---")

    # Update gist or local file
    print("\n--- Publishing ---")
    update_gist(output)

    # Also write to repo data folder
    output_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'news-latest.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"Also written to {output_path}")

    print("\nDone!")


if __name__ == '__main__':
    main()
