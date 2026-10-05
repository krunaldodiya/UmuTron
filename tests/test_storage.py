"""Inert volume observations and temporary SQLite only; never touch real drives."""
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
import sqlite3
import multiprocessing
import json
from uuid import uuid4

from game_library.storage import (StorageError, StorageModel, StateStore,
                                  Volume, SizePlan, UnavailableStorage)


def reserve_process(path, volumes, install, barrier, queue):
    model = StorageModel(StateStore(path), lambda: volumes)
    barrier.wait(timeout=10)
    try:
        model.reserve(str(uuid4()), 1, install, SizePlan(100, 200)); queue.put(True)
    except StorageError: queue.put(False)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='umutron-storage-test-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'storage.sqlite3'
        self.volumes = [Volume('fs-cache', 'mount-1', '/fixture/cache', 'Cache SSD', 1000, 2000),
                        Volume('fs-install', 'mount-2', '/fixture/games', 'Games SSD', 1000, 2000)]
        self.model = StorageModel(StateStore(self.path), lambda: list(self.volumes))
        self.cache = self.model.register(self.volumes[0], 'cache')
        self.install = self.model.register(self.volumes[1], 'install')
        self.plan = SizePlan(100, 200)

    def reserve(self, plan=None, job=None, generation=1):
        return self.model.reserve(job or str(uuid4()), generation, self.install, plan or self.plan)

    def test_registry_root_default_and_metadata_only_removal(self):
        sentinel = Path(self.temp.name) / 'Games' / 'legacy.exe'
        sentinel.parent.mkdir(); sentinel.write_text('preserve')
        data = self.model.snapshot()
        self.assertEqual(data['default_install'], self.install)
        row = next(x for x in data['registrations'] if x['id'] == self.install)
        self.assertEqual(row['path'], '/fixture/games/EmuGames')
        self.assertFalse(Path('/fixture/games').exists())
        self.model.remove(self.install)
        self.assertEqual(sentinel.read_text(), 'preserve')
        self.assertIsNone(self.model.snapshot()['default_install'])
        self.assertEqual(StorageModel(StateStore(self.path), lambda: self.volumes).snapshot(), self.model.snapshot())

    def test_one_cache_duplicate_role_and_default(self):
        with self.assertRaises(StorageError): self.model.register(self.volumes[0], 'cache')
        extra = self.model.add_role(self.cache, 'install')
        self.model.set_default(extra)
        self.assertEqual(self.model.snapshot()['default_install'], extra)
        self.assertEqual(extra,self.cache)
        self.assertEqual(len(self.model.snapshot()['registrations']),2)
        with self.assertRaises(StorageError):self.model.register(self.volumes[0],'install')
        with self.assertRaises(StorageError): self.model.register(replace(self.volumes[0], root='/fixture/cache/nested'), 'install')

    def test_exact_formula_separate_and_same_volume(self):
        quote = self.model.quote(self.install, SizePlan(101, 201, 7, 11))
        self.assertTrue(quote.fits)
        self.assertEqual([r.required for r in quote.volumes], [108, 313])
        self.model.remove(self.install)
        self.install = self.model.add_role(self.cache, 'install')
        quote = self.model.quote(self.install, SizePlan(101, 201, 7, 11, 5))
        self.assertEqual(len(quote.volumes), 1)
        self.assertEqual((quote.volumes[0].required, quote.volumes[0].floor), (421, 5))

    def test_shared_role_one_row_one_budget_and_active_role_cannot_be_removed(self):
        self.model.remove(self.install);self.install=self.model.add_role(self.cache,'install')
        rows=self.model.snapshot()['registrations'];self.assertEqual(len(rows),1)
        self.assertEqual(set(rows[0]['roles']),{'cache','install'})
        self.assertEqual(self.model.choices()['registered'],{'fs-cache'})
        token=self.reserve();quote=self.model.revalidate(token,'start')
        self.assertEqual(len(quote.volumes),1);self.assertEqual(quote.volumes[0].required,400)
        for role in ('cache','install'):
            with self.assertRaises(StorageError):self.model.remove_role(self.install,role)
        self.model.release(token,confirmed_stopped=True);self.model.remove_role(self.install,'cache')
        self.assertEqual(self.model.snapshot()['registrations'][0]['roles'],['install'])

    def test_canceled_registration_and_duplicate_volume_state_are_rejected(self):
        extra=Volume('other-partition','mount-3','/fixture/other','Another partition',1000,2000);self.volumes.append(extra)
        before=self.model.snapshot()
        with self.assertRaisesRegex(StorageError,'canceled'):self.model.register(extra,'install',cancelled=lambda:True)
        self.assertEqual(self.model.snapshot(),before)
        with self.assertRaisesRegex(StorageError,'invalid or unsupported'):
            with self.model.store.transaction() as state:
                duplicate=dict(state['registrations'][0],id=str(uuid4()),roles=['install'])
                state['registrations'].append(duplicate)

    def test_both_volumes_gate_exact_and_one_short(self):
        for index, limit in ((0, 100), (1, 300)):
            original = self.volumes[index]
            self.volumes[index] = replace(original, free_bytes=limit - 1)
            self.assertFalse(self.model.quote(self.install, self.plan).fits)
            with self.assertRaises(StorageError): self.reserve()
            self.assertEqual(self.model.snapshot()['active_jobs'], 0)
            self.volumes[index] = replace(original, free_bytes=limit)
            token = self.reserve(); self.model.release(token, confirmed_stopped=True)
            self.volumes[index] = original

    def test_unknown_or_unverified_size_blocks_start(self):
        for plan in (SizePlan(None, 200), SizePlan(100, None), SizePlan(100, 200, verified=False)):
            self.assertIsNone(self.model.quote(self.install, plan).fits)
            with self.assertRaisesRegex(StorageError, 'size'): self.reserve(plan)

    def test_malformed_sizes_and_boundaries(self):
        for value in (-1, True, 1.5, '100', 2**63):
            with self.assertRaises((ValueError, StorageError)): SizePlan(value, 200)
        self.assertTrue(self.model.quote(self.install, SizePlan(0, 0)).fits)
        self.assertEqual(SizePlan(0, 1).install_required, 2)

    def test_unavailable_precedes_capacity(self):
        for changes, reason in (({'read_only':True}, 'read-only'),
                                ({'support_reason':'NTFS 0777 ancestry is unsupported'}, 'NTFS'),
                                ({'is_root':False}, 'root')):
            original = self.volumes[1]; self.volumes[1] = replace(original, **changes)
            with self.assertRaisesRegex(StorageError, reason): self.reserve(SizePlan(100, None))
            self.volumes[1] = original
        self.volumes.pop()
        with self.assertRaisesRegex(StorageError, 'offline'): self.reserve()
        self.assertEqual(self.model.snapshot()['registrations'][1]['status'], 'offline')

    def test_identity_collision_and_stale_picker(self):
        self.volumes.append(replace(self.volumes[1], mount_id='mount-3', root='/other'))
        with self.assertRaisesRegex(StorageError, 'ambiguous'): self.reserve()
        self.volumes.pop()
        old = self.volumes[0]; self.volumes[0] = replace(old, mount_id='mount-new')
        with self.assertRaisesRegex(StorageError, 'changed'): self.model.register(old, 'install')

    def test_active_token_never_rebinds_after_remount(self):
        token = self.reserve()
        self.volumes[1] = replace(self.volumes[1], root='/fixture/new', mount_id='mount-new')
        self.assertEqual(self.model.snapshot()['registrations'][1]['path'], '/fixture/new/EmuGames')
        with self.assertRaisesRegex(StorageError, 'changed'): self.model.revalidate(token, 'extraction')
        with self.assertRaisesRegex(StorageError, 'changed'): self.model.reconcile(token, 1, 1)
        self.assertEqual(self.model.snapshot()['active_jobs'], 1)

    def test_rechecks_space_before_resume_and_extraction(self):
        token = self.reserve()
        self.volumes[1] = replace(self.volumes[1], free_bytes=299)
        for phase in ('resume', 'extraction', 'commit'):
            with self.assertRaises(StorageError): self.model.revalidate(token, phase)
        self.assertEqual(self.model.snapshot()['active_jobs'], 1)

    def test_reconciliation_retains_margin_not_progress_credit(self):
        token = self.reserve()
        self.volumes[0] = replace(self.volumes[0], free_bytes=900)
        self.volumes[1] = replace(self.volumes[1], free_bytes=800)
        self.model.reconcile(token, 100, 200)
        quote = self.model.revalidate(token, 'extraction')
        self.assertEqual([r.required for r in quote.volumes], [0, 100])
        with self.assertRaises(StorageError): self.model.reconcile(token, 101, 200)
        with self.assertRaises(StorageError): self.model.reconcile(token, 100, 201)
        with self.assertRaises(TypeError): self.model.reconcile(token, bytes_done=100)
        with self.assertRaises(StorageError): self.model.revalidate(replace(token, nonce=str(uuid4())), 'resume')

    def test_idempotency_conflict_release_and_retained_files(self):
        job = str(uuid4()); token = self.reserve(job=job)
        self.assertEqual(token, self.reserve(job=job))
        with self.assertRaises(StorageError): self.reserve(SizePlan(101, 200), job)
        with self.assertRaises(StorageError): self.reserve(job=job, generation=2)
        for method in (lambda: self.model.remove(self.cache), lambda: self.model.remove(self.install),
                       lambda: self.model.release(token, confirmed_stopped=False)):
            with self.assertRaises(StorageError): method()
        self.assertEqual(self.model.snapshot()['active_jobs'], 1)
        partial = Path(self.temp.name) / 'retained-archive'; partial.write_text('partial')
        self.model.release(token, confirmed_stopped=True)
        self.assertEqual(partial.read_text(), 'partial')
        with self.assertRaises(StorageError): self.reserve(job=job)
        self.reserve(job=job, generation=2)

    def test_concurrent_admission_and_shared_floor(self):
        self.volumes[1] = replace(self.volumes[1], free_bytes=650)
        barrier = threading.Barrier(4); outcomes = []; lock = threading.Lock()
        def run():
            model = StorageModel(StateStore(self.path), lambda: list(self.volumes))
            barrier.wait()
            try: model.reserve(str(uuid4()), 1, self.install, SizePlan(100, 200, additional_floor=50)); result=True
            except StorageError: result=False
            with lock: outcomes.append(result)
        threads = [threading.Thread(target=run) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5); self.assertFalse(thread.is_alive())
        self.assertEqual(outcomes.count(True), 2)
        self.assertEqual(self.model.snapshot()['active_jobs'], 2)

    def test_transaction_rollback_and_corrupt_state_preserved(self):
        before = self.model.snapshot()
        with self.assertRaises(RuntimeError):
            with self.model.store.transaction() as state:
                state['registrations'].clear(); raise RuntimeError('interrupted')
        self.assertEqual(self.model.snapshot(), before)
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE storage SET data = json_set(data, '$.version', 999)")
        damaged = self.path.read_bytes()
        with self.assertRaises(StorageError): self.model.snapshot()
        self.assertEqual(self.path.read_bytes(), damaged)

    def test_separate_processes_share_the_same_ledger(self):
        self.volumes[1] = replace(self.volumes[1], free_bytes=599)
        context = multiprocessing.get_context('spawn'); barrier = context.Barrier(3); queue = context.Queue()
        processes = [context.Process(target=reserve_process, args=(self.path, self.volumes, self.install, barrier, queue)) for _ in range(3)]
        for process in processes: process.start()
        for process in processes:
            process.join(15)
            if process.is_alive(): process.terminate(); process.join(); self.fail('Storage process did not complete.')
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sum(queue.get(timeout=2) for _ in processes), 1)
        queue.close(); queue.join_thread()

    def test_save_failure_rolls_back_entire_reservation(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TRIGGER fail_save BEFORE INSERT ON storage BEGIN SELECT RAISE(ABORT, 'fixture failed save'); END")
        with self.assertRaisesRegex(StorageError, 'saved'): self.reserve()
        self.assertEqual(self.model.snapshot()['active_jobs'], 0)

    def test_unavailable_cache_and_missing_registration(self):
        self.volumes[0] = replace(self.volumes[0], read_only=True)
        with self.assertRaisesRegex(StorageError, 'read-only'): self.reserve()
        self.model.remove(self.cache)
        with self.assertRaisesRegex(StorageError, 'cache'): self.reserve()

    def test_shared_pool_cannot_pass_two_separate_checks(self):
        self.model.remove(self.install); self.install = self.model.add_role(self.cache, 'install')
        self.volumes[0] = replace(self.volumes[0], free_bytes=399)
        quote = self.model.quote(self.install, self.plan)
        self.assertEqual(len(quote.volumes), 1); self.assertFalse(quote.fits)
        with self.assertRaises(StorageError): self.reserve()

    def test_missing_persisted_plan_fields_fail_closed_without_rewrite(self):
        token = self.reserve(SizePlan(100, 200, 10, 500, 77))
        with sqlite3.connect(self.path) as connection:
            original = connection.execute('SELECT data FROM storage WHERE id=1').fetchone()[0]
        for field in ('cache_extra', 'install_extra', 'additional_floor', 'verified'):
            state = json.loads(original); del state['jobs'][f'{token.job_id}:1']['plan'][field]
            with sqlite3.connect(self.path) as connection:
                connection.execute('UPDATE storage SET data=? WHERE id=1', (json.dumps(state),))
            before = self.path.read_bytes()
            with self.assertRaisesRegex(StorageError, 'invalid or unsupported'):
                self.model.revalidate(token, 'extraction')
            self.assertEqual(self.path.read_bytes(), before, field)

    def test_unknown_persisted_plan_field_preserves_state(self):
        token = self.reserve()
        with sqlite3.connect(self.path) as connection:
            state = json.loads(connection.execute('SELECT data FROM storage WHERE id=1').fetchone()[0])
            state['jobs'][f'{token.job_id}:1']['plan']['new_policy'] = 0
            connection.execute('UPDATE storage SET data=? WHERE id=1', (json.dumps(state),))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError): self.model.snapshot()
        self.assertEqual(self.path.read_bytes(), before)

    def test_explicit_unavailable_service_cannot_register_or_reserve(self):
        service = UnavailableStorage()
        self.assertFalse(service.enabled)
        self.assertEqual(service.snapshot()['registrations'], [])
        with self.assertRaises(StorageError): service.register(self.volumes[0], 'cache')


if __name__ == '__main__': unittest.main()
