"""Common query and filtering behavior for download source adapters."""
import json
import os
import re
import unicodedata
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from .model import DownloadRelease



def normalize_title(title):
    if not title or not isinstance(title, str):
        return ''
    normalized = unicodedata.normalize('NFKD', title)
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))
    normalized = normalized.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    return normalized.replace('–', '-').replace('—', '-').strip()


def build_search_queries(title):
    normalized = normalize_title(title)
    if not normalized:
        return []
    queries = [normalized]
    if "'" in normalized:
        queries.append(normalized.replace("'", '’'))
    if ':' in normalized:
        queries.extend((normalized.replace(':', ''), normalized.replace(':', ' - ')))
    for separator in (':', ' - '):
        if separator in normalized:
            base = normalized.split(separator)[0].strip()
            if len(base) > 2 and base not in queries:
                queries.append(base)
    roman_map = ((r'\bVIII\b', '8'), (r'\bVII\b', '7'), (r'\bVI\b', '6'),
                 (r'\bIV\b', '4'), (r'\bV\b', '5'), (r'\bIII\b', '3'), (r'\bII\b', '2'))
    roman_variant = normalized
    for pattern, arabic in roman_map:
        roman_variant = re.sub(pattern, arabic, roman_variant)
    if roman_variant != normalized and roman_variant not in queries:
        queries.append(roman_variant)
    return queries

MULTIPART_FILE_PATTERNS = (
    re.compile(r'(?i)\.part\d+\.(?:rar|7z|zip|exe|bin)$'),
    re.compile(r'(?i)\.7z\.\d{3}$'),
    re.compile(r'(?i)\.(?:zip|rar)\.\d{3}$'),
    re.compile(r'(?i)\.[rz]\d{2}$'),
    re.compile(r'(?i)\.001$'),
)

MULTIPART_TITLE_PATTERNS = (
    re.compile(r'(?i)\b(?:part|cd|disc|dvd)\s*\d+\s*(?:of|/)\s*\d+\b'),
    re.compile(r'(?i)\[part\s*\d+\s*(?:of|/)\s*\d+\]'),
    re.compile(r'(?i)\(part\s*\d+\s*(?:of|/)\s*\d+\)'),
    re.compile(r'(?i)\.part\d+\.(?:rar|7z|zip|exe)\b'),
    re.compile(r'(?i)\.7z\.\d{3}\b'),
    re.compile(r'(?i)\.(?:rar|zip)\.\d{3}\b'),
)


def is_multipart_link(uri):
    """Return True if the URI points to a split / multi-part archive segment."""
    if not uri or not isinstance(uri, str):
        return False
    try:
        parsed = urlparse(uri)
    except Exception:
        return False
    filename = ''
    if parsed.scheme == 'magnet':
        qs = parse_qs(parsed.query)
        dn = qs.get('dn', [''])[0]
        filename = unquote(dn)
    else:
        path = unquote(parsed.path)
        filename = path.rstrip('/').split('/')[-1] if path else ''

    if filename:
        for pattern in MULTIPART_FILE_PATTERNS:
            if pattern.search(filename):
                return True
    return False


def is_multipart_title(title):
    """Return True if the release title denotes an individual split / multi-part volume."""
    if not title or not isinstance(title, str):
        return False
    for pattern in MULTIPART_TITLE_PATTERNS:
        if pattern.search(title):
            return True
    return False


def is_multipart_release(title, uris):
    """Return True if the title or any associated link represents a split / multi-part archive."""
    if is_multipart_title(title):
        return True
    if isinstance(uris, (list, tuple)):
        for uri in uris:
            if is_multipart_link(uri):
                return True
    return False


class BaseSourceProvider:
    id = ''
    name = ''
    priority = 100
    install_strategy = 'installer'

    def filter_candidates(self, items):
        return [item for item in items if 'patch from' not in item.get('title', '').lower()]

    def get_install_strategy(self, item):
        return self.install_strategy

    def search(self, base_url, title, api_key=None, transport=None):
        if not base_url or not title:
            return []
        key = api_key or os.environ.get('UMUTRON_API_KEY') or os.environ.get('INTERNAL_API_KEY')
        seen_queries = set()
        for query in build_search_queries(title):
            clean_query = query.strip()
            if not clean_query or clean_query in seen_queries:
                continue
            seen_queries.add(clean_query)
            params = urlencode({'link_type': 'magnet', 'source_name': self.id, 'q': clean_query, 'limit': 10})
            endpoint = f"{base_url.rstrip('/')}/api/downloads?{params}"
            try:
                if transport is not None:
                    data = transport(endpoint)
                else:
                    headers = {
                        'Accept': 'application/json',
                        'User-Agent': 'UmuTron/compatibility-adapter',
                    }
                    if key:
                        headers['x-api-key'] = key
                    request = Request(endpoint, headers=headers)
                    with build_opener(ProxyHandler({})).open(request, timeout=15) as response:
                        data = json.loads(response.read().decode('utf-8'))
                results = []
                for item in self.filter_candidates(data.get('data', [])):
                    uris = item.get('uris', [])
                    magnet = next((uri for uri in uris if uri.startswith('magnet:')), None)
                    if not magnet:
                        continue
                    results.append(DownloadRelease(
                        provider_id=self.id,
                        provider_name=self.name,
                        title=item.get('title', title),
                        file_size=item.get('file_size') or 'Unknown size',
                        magnet=magnet,
                        uris=uris,
                        install_strategy=self.get_install_strategy(item),
                        upload_date=item.get('upload_date'),
                        raw=item,
                    ))
                if results:
                    return results
            except Exception:
                continue
        return []
