"""Built-in source adapters, each maintained in its own provider directory."""
from .ankergames.provider import AnkerGamesProvider
from .byxatab.provider import ByXatabProvider
from .dodi.provider import DODIProvider
from .fitgirl.provider import FitGirlProvider


def default_providers():
    return (FitGirlProvider(), ByXatabProvider(), DODIProvider(), AnkerGamesProvider())


__all__ = ['AnkerGamesProvider', 'ByXatabProvider', 'DODIProvider', 'FitGirlProvider', 'default_providers']
