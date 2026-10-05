from copy import deepcopy
import unittest

from game_library.collection import genre_choices, library_page, page_numbers


class LocalCollectionTests(unittest.TestCase):
    def games(self, count=211):
        return [{'id': str(i), 'title': f'Game {i:03}',
                 'genres': 'Action, Adventure' if i % 2 else 'Puzzle'}
                for i in range(count)]

    def test_combined_filter_runs_over_whole_library_before_pagination(self):
        games = self.games()
        result = library_page(games, 'GAME', 'action', page=2)
        self.assertEqual(result['count'], 105)
        self.assertEqual(result['pages'], 3)
        self.assertEqual([g['id'] for g in result['items']], [str(i) for i in range(97, 193, 2)])
        self.assertEqual(library_page(games, 'Game 20', 'action')['count'], 5)

    def test_page_is_bounded_and_clamps_after_last_page_removal(self):
        games = self.games(97)
        self.assertEqual(len(library_page(games, page=3)['items']), 1)
        result = library_page(games[:-1], page=3)
        self.assertEqual((result['page'], len(result['items'])), (2, 48))
        self.assertEqual(library_page(games, page=-1)['page'], 1)

    def test_genres_are_local_case_insensitive_exact_labels_and_not_substrings(self):
        games = [{'id': '1', 'title': 'One', 'genres': ' Action, Role-playing (RPG); action\n  Puzzle  '},
                 {'id': '2', 'title': 'Two', 'genres': 'Action-adventure'},
                 {'id': '3', 'title': 'Three', 'genres': ''}]
        self.assertEqual([key for key, _ in genre_choices(games)],
                         ['action', 'action-adventure', 'puzzle', 'role-playing (rpg)'])
        self.assertEqual([g['id'] for g in library_page(games, genre='action')['items']], ['1'])
        self.assertEqual(library_page(games)['count'], 3)

    def test_empty_matches_and_removed_selected_genre_stay_empty(self):
        games = self.games()
        self.assertIn(('missing', 'missing'), genre_choices(games, 'missing'))
        result = library_page(games, genre='missing', page=9)
        self.assertEqual((result['items'], result['count'], result['page'], result['pages']), ([], 0, 1, 1))
        self.assertEqual(library_page([])['total'], 0)

    def test_sort_applies_before_slicing_and_does_not_mutate_saved_records(self):
        games = self.games(); before = deepcopy(games)
        self.assertEqual(library_page(games, sort=1, page=2)['items'][0]['id'], '162')
        self.assertEqual(library_page(games, sort=2, genre='action')['items'][0]['id'], '209')
        self.assertEqual(games, before)

    def test_numbered_window_is_bounded_and_unknown_total_does_not_invent_pages(self):
        self.assertEqual(page_numbers(1, 1), [1])
        self.assertEqual(page_numbers(1, 8), [1, 2, 3, 4, 5, None])
        self.assertEqual(page_numbers(5, 9), [None, 3, 4, 5, 6, 7, None])
        self.assertEqual(page_numbers(9, 9), [None, 5, 6, 7, 8, 9])
        self.assertEqual(page_numbers(3), [3])
        self.assertEqual(len([n for n in page_numbers(500, 100000) if n]), 5)


if __name__ == '__main__':
    unittest.main()
