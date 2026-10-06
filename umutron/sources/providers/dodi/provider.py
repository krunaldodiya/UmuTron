"""DODI installer repacks."""
from ...base import BaseSourceProvider


class DODIProvider(BaseSourceProvider):
    id = 'dodi'
    name = 'DODI'
    priority = 20
    install_strategy = 'installer'

    def filter_candidates(self, items):
        return [item for item in items if 'patch' not in item.get('title', '').lower()]
