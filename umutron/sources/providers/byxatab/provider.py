"""ByXatab loose preinstalled games and installer repacks."""
from ...base import BaseSourceProvider


class ByXatabProvider(BaseSourceProvider):
    id = 'byxatab'
    name = 'ByXatab'
    priority = 15
    install_strategy = 'portable'

    def filter_candidates(self, items):
        candidates = [item for item in items
                      if 'patch from' not in item.get('title', '').lower()
                      and 'патч' not in item.get('title', '').lower()]
        loose = [item for item in candidates
                 if 'папка игры' in item.get('title', '').lower()
                 or 'папка' in item.get('title', '').lower()]
        return loose or candidates

    def get_install_strategy(self, item):
        title = item.get('title', '').lower()
        if 'папка' in title or 'portable' in title:
            return 'portable'
        if 'repack' in title or 'репак' in title:
            return 'installer'
        return 'portable'
