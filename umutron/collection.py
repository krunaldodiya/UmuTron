"""Local Library browsing; never depends on a catalog or network transport."""
import re

LIBRARY_PAGE_SIZE = 48


def page_numbers(page, pages=None):
    """At most five numbered buttons, with honest unknown-total fallback."""
    if pages is None:
        return [page]
    start = max(1, min(page - 2, pages - 4))
    end = min(pages, start + 4)
    return ([None] if start > 1 else []) + list(range(start, end + 1)) + ([None] if end < pages else [])


def game_genres(game):
    """Read legacy and catalog genre labels without rewriting saved metadata."""
    return {' '.join(label.split()).casefold(): ' '.join(label.split())
            for label in re.split(r'[,;\n]', game.get('genres', '')) if label.strip()}


def genre_choices(games, selected=None):
    choices = {}
    for game in games:
        for key, label in game_genres(game).items():
            choices.setdefault(key, label)
    # Keep a removed genre selected until the user clears it; never widen results.
    if selected:
        choices.setdefault(selected, selected)
    return sorted(choices.items(), key=lambda item: item[0])


def library_page(games, query='', genre=None, sort=0, page=1):
    query = query.strip().casefold()
    shown = [game for game in games if query in game['title'].casefold()
             and (genre is None or genre in game_genres(game))]
    if sort == 2:
        shown.reverse()
    else:
        shown.sort(key=lambda game: game['title'].casefold(), reverse=sort == 1)
    pages = max(1, (len(shown) + LIBRARY_PAGE_SIZE - 1) // LIBRARY_PAGE_SIZE)
    page = max(1, min(page, pages))
    start = (page - 1) * LIBRARY_PAGE_SIZE
    return {'items': shown[start:start + LIBRARY_PAGE_SIZE], 'page': page,
            'pages': pages, 'count': len(shown), 'total': len(games)}
