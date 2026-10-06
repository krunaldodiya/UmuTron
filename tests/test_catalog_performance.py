from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import base64
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from game_library.catalog import CatalogService, RemoteCatalog
from game_library.catalog_work import BoundedWork, CatalogWork


def page(number=1, identity=1):
    return {'items': [{'id': identity, 'name': 'Fixture game', 'images': {}, 'genres': []}],
            'page': number, 'has_next': False}


class CachePerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []
        def transport(url):
            self.calls.append(url)
            return [{'id': 5, 'name': 'Shooter'}] if url.endswith('/genres') else page()
        self.transport = transport
        self.provider = RemoteCatalog('https://one.example', transport)
        self.service = CatalogService(self.provider, self.root)

    def test_warm_and_reopened_snapshots_need_no_provider_call(self):
        self.assertIsNone(self.service.cached_browse())
        self.service.browse(); self.service.genres()
        self.calls.clear()
        self.provider.transport = lambda _: self.fail('Snapshot read contacted provider')
        for service in (self.service, CatalogService(self.provider, self.root)):
            saved = service.cached_browse()
            self.assertEqual(saved['items'][0]['id'], 1)
            self.assertTrue(saved['cached']); self.assertTrue(saved['refreshing'])
            self.assertEqual(service.cached_genres(), [{'id': 5, 'name': 'Shooter'}])
        self.assertEqual(self.calls, [])

    def test_origin_query_genre_and_page_keys_do_not_mix(self):
        self.service.browse()
        self.assertIsNone(self.service.cached_browse('other'))
        self.assertIsNone(self.service.cached_browse('', 5))
        self.assertIsNone(self.service.cached_browse('', None, 2))
        other = CatalogService(RemoteCatalog('https://two.example', self.transport), self.root)
        self.assertIsNone(other.cached_browse())
        # Old unscoped snapshots are never adopted by the configured origin.
        for path in self.root.glob('*.json'): path.unlink()
        (self.root / 'legacy.json').write_text(json.dumps({'at': 1, 'value': page()}))
        self.assertIsNone(self.service.cached_browse())

    def test_cache_envelope_and_payload_are_revalidated(self):
        self.service.browse()
        path = next(self.root.glob('*.json')); original = path.read_text()
        defects = [lambda d: d.update(scope='remote:https://other.example'),
                   lambda d: d.update(key='other'), lambda d: d.update(at=True),
                   lambda d: d.update(at=10**20), lambda d: d.update(at=-1),
                   lambda d: d['value'].update(page=2),
                   lambda d: d['value'].update(total_items=1),
                   lambda d: d['value']['items'][0].update(id=True)]
        for defect in defects:
            with self.subTest(defect=defect):
                value = json.loads(original); defect(value); path.write_text(json.dumps(value))
                self.assertIsNone(self.service.cached_browse())
        for raw in ('{', '[' * 2000, ' ' * (4 * 1024 * 1024 + 1)):
            path.write_text(raw); self.assertIsNone(self.service.cached_browse())

    def test_refresh_failure_retains_validated_snapshot_and_marks_offline(self):
        self.service.browse()
        self.provider.transport = lambda _: (_ for _ in ()).throw(OSError('offline'))
        offline = self.service.browse()
        self.assertTrue(offline['cached']); self.assertNotIn('refreshing', offline)
        self.assertEqual(offline['items'][0]['id'], 1)
        self.assertIsNotNone(self.service.cached_browse())

    def test_nonregular_snapshot_is_a_nonblocking_cache_miss(self):
        self.service.browse(); path=next(self.root.glob('*.json'))
        path.unlink(); os.mkfifo(path)
        self.assertIsNone(self.service.cached_browse())
        path.unlink(); target=self.root/'outside'; target.write_text('private fixture')
        path.symlink_to(target)
        self.assertIsNone(self.service.cached_browse()); self.assertEqual(target.read_text(),'private fixture')

    def test_metadata_eviction_remains_bounded(self):
        for index in range(105): (self.root/f'old-{index}.json').write_text('{}')
        self.service.browse()
        self.assertLessEqual(len(list(self.root.glob('*.json'))),100)
        self.assertEqual(self.service.cached_browse()['items'][0]['id'],1)

    def test_snapshot_and_unrelated_metadata_complete_while_image_is_held(self):
        self.service.browse()
        entered = threading.Event(); release = threading.Event()
        def image_work(*_):
            entered.set(); self.assertTrue(release.wait(3))
            return base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1kAAAAASUVORK5CYII=')
        self.service.image_transport = image_work
        with ThreadPoolExecutor(max_workers=2) as pool:
            image = pool.submit(self.service.image, 'https://images.igdb.com/igdb/image/upload/t_cover_big/fixture.jpg')
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.service.cached_browse()['items'][0]['id'], 1)
                self.assertEqual(pool.submit(self.service.genres).result(1)[0]['id'], 5)
                self.assertFalse(image.done())
            finally: release.set()
            self.assertTrue(image.result(2).is_file())

    def test_same_key_refresh_shares_transport_and_returns_independent_values(self):
        entered = threading.Event(); release = threading.Event(); follower = threading.Event()
        def transport(url):
            self.calls.append(url); entered.set(); self.assertTrue(release.wait(3)); return page()
        self.provider.transport = transport
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.service.browse)
            try:
                self.assertTrue(entered.wait(2))
                with self.service.flight_lock:
                    flight = next(iter(self.service.flights.values()))
                    result = flight.result
                    def waiting(*args, **kwargs):
                        follower.set(); return result(*args, **kwargs)
                    flight.result = waiting
                second = pool.submit(self.service.browse)
                self.assertTrue(follower.wait(2)); self.assertEqual(len(self.calls), 1)
            finally: release.set()
            a, b = first.result(2), second.result(2)
        a['items'][0]['name'] = 'Enriched only in one caller'
        self.assertEqual(b['items'][0]['name'], 'Fixture game')
        self.assertEqual(len(self.calls), 1); self.assertEqual(self.service.flights, {})

    def test_distinct_refresh_flights_are_bounded_and_failures_release_ownership(self):
        condition=threading.Condition();release=threading.Event();entered=[]
        def transport(url):
            with condition:entered.append(url);condition.notify_all()
            self.assertTrue(release.wait(3));return page()
        self.provider.transport=transport
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures=[pool.submit(self.service.browse,f'query-{index}') for index in range(8)]
            try:
                with condition:self.assertTrue(condition.wait_for(lambda:len(entered)==8,2))
                with self.assertRaisesRegex(ValueError,'busy'):self.service.browse('over-limit')
                self.assertEqual(len(entered),8)
            finally:release.set()
            for future in futures:self.assertEqual(future.result(2)['items'][0]['id'],1)
        self.assertEqual(self.service.flights,{})
        self.provider.transport=lambda _:(_ for _ in ()).throw(OSError('offline'))
        with self.assertRaises(OSError):self.service.browse('uncached-failure')
        self.assertEqual(self.service.flights,{})

    def test_bad_image_cache_is_refetched_without_weakening_url_validation(self):
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1kAAAAASUVORK5CYII=')
        calls=[]
        def image(url,limit):calls.append(url);return png
        self.service.image_transport=image
        url='https://images.igdb.com/igdb/image/upload/t_cover_big/fixture.jpg'
        path=self.service.image(url);path.write_bytes(b'invalid cached image')
        self.assertEqual(self.service.image(url).read_bytes(),png);self.assertEqual(len(calls),2)
        self.service.image(url);self.assertEqual(len(calls),2)
        with self.assertRaises(ValueError):self.service.image('https://elsewhere.example/fixture.jpg')
        self.assertEqual(len(calls),2)

    def test_cache_write_failure_does_not_hide_valid_fresh_cards(self):
        with patch('game_library.catalog.atomic_write',side_effect=OSError('read-only cache')):
            value=self.service.browse()
        self.assertFalse(value['cached']);self.assertEqual(value['items'][0]['id'],1)
        self.assertIsNone(self.service.cached_browse())

    def test_known_totals_above_request_cap_stay_exact_in_snapshot(self):
        def transport(_):
            return {'items': [], 'page': 1000, 'has_next': False,
                    'total_items': 0, 'total_pages': 1}
        self.provider.transport = transport
        self.service.browse(page=1000)
        value = self.service.cached_browse(page=1000)
        self.assertEqual(value['page'], 1000); self.assertEqual(value['total_pages'], 1)
        self.provider.transport = lambda _: {'items': [page(identity=i)['items'][0] for i in range(1,25)],
                                            'page': 1, 'has_next': True, 'total_items': 377355, 'total_pages': 15724}
        self.service.browse()
        self.assertEqual(self.service.cached_browse()['total_pages'], 15724)


class CatalogWorkTests(unittest.TestCase):
    def test_held_source_lookup_does_not_block_catalog_metadata(self):
        work=CatalogWork();entered=threading.Event();release=threading.Event()
        def held_source():
            entered.set();self.assertTrue(release.wait(3))
        source=work.submit_source(held_source)
        try:
            self.assertTrue(entered.wait(2))
            metadata=work.submit(lambda:'detail')
            self.assertEqual(metadata.result(2),'detail')
            self.assertFalse(source.done())
        finally:
            release.set();work.shutdown(wait=True,cancel_futures=True)

    def test_foreground_work_precedes_queued_optional_enrichment(self):
        work=BoundedWork(1,4,'priority-fixture');release=threading.Event();entered=threading.Event();order=[]
        def held():entered.set();self.assertTrue(release.wait(3))
        work.submit(held)
        try:
            self.assertTrue(entered.wait(2))
            work.submit(lambda:order.append('background-1'),background=True)
            work.submit(lambda:order.append('background-2'),background=True)
            work.submit(lambda:order.append('foreground'))
        finally:release.set();work.shutdown(wait=True)
        self.assertEqual(order,['foreground','background-1','background-2'])

    def test_nonblocking_shutdown_can_drain_accepted_work(self):
        work=BoundedWork(1,2,'drain-fixture');release=threading.Event();entered=threading.Event()
        def held():entered.set();self.assertTrue(release.wait(3));return 'running'
        first=work.submit(held)
        try:
            self.assertTrue(entered.wait(2));second=work.submit(lambda:'queued')
            work.shutdown(wait=False)
            self.assertFalse(second.cancelled())
        finally:release.set();work.shutdown(wait=True)
        self.assertEqual((first.result(),second.result()),('running','queued'))

    def test_queue_bound_and_cancel_free_a_pending_slot_before_running_finishes(self):
        work = BoundedWork(1, 2, 'bounded-fixture')
        entered = threading.Event(); release = threading.Event(); called = []
        def held():
            entered.set(); self.assertTrue(release.wait(3)); return 'running'
        running = work.submit(held)
        try:
            self.assertTrue(entered.wait(2))
            canceled = work.submit(lambda: called.append('canceled'), background=True)
            queued = work.submit(lambda: 'queued', background=True)
            with self.assertRaisesRegex(RuntimeError, 'busy'): work.submit(lambda: None).result()
            self.assertTrue(canceled.cancel())
            replacement = work.submit(lambda: 'replacement', background=True)
            self.assertFalse(replacement.done()); self.assertEqual(len(work.queue), 2)
        finally: release.set(); work.shutdown(wait=True)
        self.assertEqual(called, []); self.assertEqual(running.result(), 'running')
        self.assertEqual(queued.result(), 'queued'); self.assertEqual(replacement.result(), 'replacement')

    def test_images_cannot_occupy_metadata_capacity(self):
        work = CatalogWork(); release = threading.Event(); entered = [threading.Event(), threading.Event()]
        def image(index):
            entered[index].set(); self.assertTrue(release.wait(3))
        images = [work.submit_image(lambda i=i: image(i)) for i in range(2)]
        try:
            self.assertTrue(all(event.wait(2) for event in entered))
            self.assertEqual(work.submit(lambda: 'first cards').result(1), 'first cards')
            self.assertTrue(all(not future.done() for future in images))
        finally: release.set(); work.shutdown(wait=True, cancel_futures=True)

    def test_shutdown_cancels_pending_work_and_preserves_running_work(self):
        work = BoundedWork(1, 2, 'shutdown-fixture')
        entered = threading.Event(); release = threading.Event()
        def held(): entered.set(); self.assertTrue(release.wait(3)); return 'finished'
        running = work.submit(held)
        try:
            self.assertTrue(entered.wait(2)); pending = work.submit(lambda: self.fail('Canceled job ran'))
            work.shutdown(wait=False, cancel_futures=True)
            self.assertTrue(pending.cancelled()); self.assertFalse(running.done())
            with self.assertRaisesRegex(RuntimeError, 'closed'): work.submit(lambda: None)
        finally: release.set(); work.shutdown(wait=True)
        self.assertEqual(running.result(), 'finished')


if __name__ == '__main__': unittest.main()
