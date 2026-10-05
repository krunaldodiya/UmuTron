"""Native download boundary and FitGirl catalog lookup."""
import json
import os
import re
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler

DEFAULT_API_KEY = 'mysupersecretkey'


class InstallUnavailable(RuntimeError):
    pass


class UnavailableInstallService:
    reason = 'Automatic game downloads are not configured yet.'

    def availability(self, game_id, metadata_identity):
        return {'available': False, 'reason': self.reason}

    def start(self, request):
        raise InstallUnavailable(self.reason)

    def snapshot(self, job_id):
        raise InstallUnavailable('No download job exists.')

    def cancel(self, job_id):
        raise InstallUnavailable('No download job exists.')

    def resume(self, job_id):
        raise InstallUnavailable('No download job exists.')


def normalize_title(title):
    if not title or not isinstance(title, str):
        return ''
    n = unicodedata.normalize('NFKD', title)
    n = ''.join(c for c in n if not unicodedata.combining(c))
    n = n.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    n = n.replace('–', '-').replace('—', '-')
    return n.strip()


def build_search_queries(title):
    norm = normalize_title(title)
    if not norm:
        return []
    queries = [norm]
    # Curly apostrophe variant
    if "'" in norm:
        queries.append(norm.replace("'", '’'))
    if ':' in norm:
        queries.append(norm.replace(':', ''))
        queries.append(norm.replace(':', ' - '))
    for sep in (':', ' - '):
        if sep in norm:
            base = norm.split(sep)[0].strip()
            if len(base) > 2 and base not in queries:
                queries.append(base)
    # Roman numeral mapping (V -> 5, IV -> 4, etc.)
    roman_map = [
        (r'\bVIII\b', '8'), (r'\bVII\b', '7'), (r'\bVI\b', '6'),
        (r'\bIV\b', '4'), (r'\bV\b', '5'), (r'\bIII\b', '3'), (r'\bII\b', '2')
    ]
    roman_variant = norm
    for r_pat, arabic in roman_map:
        roman_variant = re.sub(r_pat, arabic, roman_variant)
    if roman_variant != norm and roman_variant not in queries:
        queries.append(roman_variant)
    return queries


def search_fitgirl_repack(base_url, title, api_key=None, transport=None):
    """Query UmuTron API for FitGirl magnet repacks matching the given game title."""
    if not base_url or not title:
        return []
    key = api_key or os.environ.get('UMUTRON_API_KEY') or os.environ.get('INTERNAL_API_KEY') or DEFAULT_API_KEY
    queries = build_search_queries(title)
    seen_queries = set()

    for query in queries:
        q_clean = query.strip()
        if not q_clean or q_clean in seen_queries:
            continue
        seen_queries.add(q_clean)

        params = urlencode({'link_type': 'magnet', 'source_name': 'fitgirl', 'q': q_clean, 'limit': 10})
        endpoint = f"{base_url.rstrip('/')}/api/downloads?{params}"

        try:
            if transport is not None:
                data = transport(endpoint)
            else:
                req = Request(endpoint, headers={'x-api-key': key, 'Accept': 'application/json',
                                                  'User-Agent': 'UmuTron/download-service'})
                with build_opener(ProxyHandler({})).open(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode('utf-8'))

            items = data.get('data', [])
            if items:
                # Filter and rank matches: prefer full releases over standalone patches
                full_releases = [it for it in items if 'patch from' not in it.get('title', '').lower()]
                candidates = full_releases if full_releases else items
                # Extract primary magnet link
                results = []
                for item in candidates:
                    uris = item.get('uris', [])
                    magnet = next((u for u in uris if u.startswith('magnet:')), None)
                    if magnet:
                        item['magnet'] = magnet
                        results.append(item)
                if results:
                    return results
        except Exception:
            continue

    return []


def configured_game(game):
    """Keep configured/unmounted games playable for the normal launch checks."""
    return bool(game.get('executable')) and (game.get('installation', {}).get('mode') != 'installer'
                                            or bool(game['installation'].get('confirmed')))


def detail_actions(game, saved, fullscreen, payload_exists=False, recovery=False):
    configured = configured_game(game)
    return {'primary': 'Play' if configured else 'Install',
            'setup': saved and configured and not fullscreen, 'remove': saved,
            'uninstall': saved and configured and payload_exists,
            'resume_uninstall': saved and recovery}
