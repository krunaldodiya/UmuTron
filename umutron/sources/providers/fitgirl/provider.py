"""FitGirl full-game installer repacks."""
from ...base import BaseSourceProvider


class FitGirlProvider(BaseSourceProvider):
    id = 'fitgirl'
    name = 'FitGirl'
    priority = 10
    install_strategy = 'installer'
