from pathlib import Path
import tempfile
import unittest

from game_library.catalog import CatalogService


class CatalogTotalsTests(unittest.TestCase):
    def service(self, value):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        class Provider:
            def browse(self, *args): return value
        return CatalogService(Provider(), Path(folder.name))

    def page(self, count=25, page=1):
        return {'items': [{'id': i + 1, 'name': f'Game {i}'}
                          for i in range((page - 1) * 24, min(page * 24, count))],
                'page': page, 'has_next': page * 24 < count and page < 1000,
                'total_items': count, 'total_pages': max(1, (count + 23) // 24)}

    def test_exact_totals_and_cache_preserve_zero_and_partial_last_pages(self):
        for count, page in ((0, 1), (25, 2), (48, 2), (1, 5)):
            with self.subTest(count=count, page=page):
                service = self.service(self.page(count, page)); result = service.browse(page=page)
                self.assertEqual(result['total_items'], count)
                self.assertEqual(result['total_pages'], max(1, (count + 23) // 24))
                service.provider.browse = lambda *_: (_ for _ in ()).throw(OSError('offline'))
                self.assertEqual(service.browse(page=page)['total_items'], count)

    def test_legacy_unknown_total_stays_unknown(self):
        value = self.page(); value.pop('total_items'); value.pop('total_pages')
        result = self.service(value).browse()
        self.assertNotIn('total_items', result); self.assertNotIn('total_pages', result)

    def test_totals_reject_malformed_inconsistent_and_partial_fields(self):
        valid = self.page()
        bad = [dict(valid, total_items=True), dict(valid, total_items=-1),
               dict(valid, total_items=9007199254740992), dict(valid, total_items=25.0),
               dict(valid, total_pages=1), dict(valid, total_pages=True),
               dict(valid, has_next=False), dict(valid, items=[])]
        for key in ('total_items', 'total_pages'):
            value = dict(valid); value.pop(key); bad.append(value)
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.service(value).browse()

    def test_actual_total_is_not_clamped_to_request_cap(self):
        result = self.service(self.page(24025, 1000)).browse(page=1000)
        self.assertEqual(result['total_pages'], 1002)
        self.assertFalse(result['has_next'])


if __name__ == '__main__':
    unittest.main()
