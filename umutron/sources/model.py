"""Release data shared by the source-provider adapters."""
import re


def parse_size_bytes(size_str):
    if not size_str or not isinstance(size_str, str):
        return 0
    value = re.sub(r'\(.*?\)', '', size_str).strip()
    parts = value.split('/')
    match = re.search(r'(gb|mb|tb|kb)', value, re.IGNORECASE)
    default_unit = match.group(1).upper() if match else 'GB'
    max_bytes = 0
    for part in parts:
        found = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(gb|mb|tb|kb)?', part, re.IGNORECASE)
        if found:
            amount = float(found.group(1))
            unit = (found.group(2) or default_unit).upper()
            multiplier = {'TB': 1024**4, 'GB': 1024**3, 'MB': 1024**2, 'KB': 1024}.get(unit, 1024**3)
            max_bytes = max(max_bytes, int(amount * multiplier))
    return max_bytes


class DownloadRelease:
    def __init__(self, provider_id, provider_name, title, file_size, magnet, uris=None,
                 install_strategy='installer', upload_date=None, raw=None):
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.title = title
        self.file_size = file_size
        self.size_bytes = parse_size_bytes(file_size)
        self.magnet = magnet
        self.uris = uris or ([magnet] if magnet else [])
        self.install_strategy = install_strategy
        self.upload_date = upload_date
        self.raw = raw or {}

    def __getitem__(self, key):
        if hasattr(self, key):
            value = getattr(self, key)
            if value is not None:
                return value
        return self.raw.get(key)

    def get(self, key, default=None):
        if hasattr(self, key):
            value = getattr(self, key)
            if value is not None:
                return value
        return self.raw.get(key, default)

    def to_dict(self):
        result = dict(self.raw)
        result.update({
            'provider_id': self.provider_id,
            'provider_name': self.provider_name,
            'title': self.title,
            'file_size': self.file_size,
            'size_bytes': self.size_bytes,
            'magnet': self.magnet,
            'uris': self.uris,
            'install_strategy': self.install_strategy,
            'upload_date': self.upload_date,
        })
        return result

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or not data:
            return None
        return cls(
            provider_id=data.get('provider_id', 'unknown'),
            provider_name=data.get('provider_name', 'Unknown'),
            title=data.get('title', ''),
            file_size=data.get('file_size', 'Unknown size'),
            magnet=data.get('magnet', ''),
            uris=data.get('uris', []),
            install_strategy=data.get('install_strategy', 'installer'),
            upload_date=data.get('upload_date'),
            raw=data,
        )
