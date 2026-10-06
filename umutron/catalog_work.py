"""Bounded catalog queues; canceled pending work releases its slot immediately."""
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
import threading


class BoundedWork:
    def __init__(self, workers, pending, name):
        self.workers = workers
        self.limit = pending
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
        self.condition = threading.Condition(threading.RLock())
        self.queue = deque()
        self.running = 0
        self.closed = False

    def submit(self, work, *, background=False):
        future = Future()
        with self.condition:
            if self.closed:
                raise RuntimeError('Catalog work is closed.')
            if len(self.queue) >= self.limit:
                future.set_exception(RuntimeError('Catalog is busy. Try again shortly.'))
                return future
            task = (future, work)
            if background:
                self.queue.append(task)
            else:
                self.queue.appendleft(task)
            future.add_done_callback(self._canceled)
            self._pump()
        return future

    def _canceled(self, future):
        if not future.cancelled():
            return
        with self.condition:
            self.queue = deque(task for task in self.queue if task[0] is not future)
            self.condition.notify_all()

    def _pump(self):
        while self.running < self.workers and self.queue:
            future, work = self.queue.popleft()
            if not future.set_running_or_notify_cancel():
                continue
            self.running += 1
            self.pool.submit(self._run, future, work)

    def _run(self, future, work):
        try:
            try:
                result = work()
            except BaseException as error:
                future.set_exception(error)
            else:
                future.set_result(result)
        finally:
            with self.condition:
                self.running -= 1
                self._pump()
                if self.closed and not self.running and not self.queue:
                    self.pool.shutdown(wait=False)
                self.condition.notify_all()

    def shutdown(self, wait=True, *, cancel_futures=False):
        with self.condition:
            self.closed = True
            if cancel_futures:
                for future, _ in list(self.queue):
                    future.cancel()
            if wait:
                self.condition.wait_for(lambda: not self.running and not self.queue)
            if not self.running and not self.queue:
                self.pool.shutdown(wait=wait)


class CatalogWork:
    """Own independent bounded lifecycles for metadata, art and source lookup."""
    def __init__(self):
        self.metadata = BoundedWork(3, 32, 'catalog-metadata')
        self.images = BoundedWork(2, 32, 'catalog-image')
        self.sources = BoundedWork(2, 16, 'source-discovery')

    def submit(self, work, *, background=False):
        return self.metadata.submit(work, background=background)

    def submit_image(self, work):
        return self.images.submit(work, background=True)

    def submit_source(self, work):
        return self.sources.submit(work, background=True)

    def shutdown(self, wait=True, *, cancel_futures=False):
        for group in (self.metadata, self.images, self.sources):
            group.shutdown(False, cancel_futures=cancel_futures)
        if wait:
            for group in (self.metadata, self.images, self.sources):
                group.shutdown(True)
