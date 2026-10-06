"""AnkerGames loose preinstalled game releases."""
from ...base import BaseSourceProvider


class AnkerGamesProvider(BaseSourceProvider):
    id = 'ankergames'
    name = 'AnkerGames'
    priority = 40
    install_strategy = 'portable'
