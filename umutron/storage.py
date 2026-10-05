"""Partition registry and isolated future archive ledger. No payload writes.

Registration is production connected; archive reservations are accounting
receipts only and are not connected to transfers or filesystem capabilities.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
from pathlib import PurePosixPath
import sqlite3
from uuid import UUID, uuid4

MAX_BYTES = 2**63 - 1
CHILDREN = {'cache': 'UmuTronCache', 'install': 'EmuGames'}


class StorageError(RuntimeError):
    pass


def integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_BYTES:
        raise StorageError(f'Invalid {name}. Use nonnegative integer bytes within the supported range.')
    return value


def text(value, name):
    if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise StorageError('Invalid ' + name + '.')
    return value


def identity(value):
    try:
        if str(UUID(value)) != value: raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise StorageError('Invalid job or registration identity.') from None
    return value


def root_path(value):
    text(value, 'mounted root')
    if not value.startswith('/') or value.startswith('//') or str(PurePosixPath(value)) != value or '..' in PurePosixPath(value).parts:
        raise StorageError('Choose a discovered mounted root.')
    return value


@dataclass(frozen=True)
class Volume:
    # volume_id is a collision-checked stable filesystem identity from the future
    # observer. mount_id must include a boot/session fence, not just a reusable ID.
    volume_id: str
    mount_id: str
    root: str
    label: str
    free_bytes: int
    total_bytes: int
    read_only: bool = False
    support_reason: str = ''
    is_root: bool = True
    managed_reason: str = ''
    device: int | None = None

    def __post_init__(self):
        text(self.volume_id, 'volume identity'); text(self.mount_id, 'mount identity')
        root_path(self.root); text(self.label, 'volume label')
        integer(self.free_bytes, 'free bytes'); integer(self.total_bytes, 'total bytes')
        if self.free_bytes > self.total_bytes: raise StorageError('Invalid volume capacity.')
        if type(self.read_only) is not bool or type(self.is_root) is not bool or not isinstance(self.support_reason, str):
            raise StorageError('Invalid volume observation.')
        if not isinstance(self.managed_reason, str): raise StorageError('Invalid managed storage support.')
        if self.device is not None: integer(self.device, 'filesystem device')

    @property
    def stamp(self):
        return {'volume_id': self.volume_id, 'mount_id': self.mount_id, 'root': self.root}

    @property
    def reason(self):
        if not self.is_root: return 'Choose a discovered mounted root.'
        if self.read_only: return 'This drive is mounted read-only.'
        return self.support_reason


@dataclass(frozen=True)
class SizePlan:
    archive_bytes: int | None
    expanded_bytes: int | None
    cache_extra: int = 0
    install_extra: int = 0
    additional_floor: int = 0
    verified: bool = True

    def __post_init__(self):
        for name in ('archive_bytes', 'expanded_bytes', 'cache_extra', 'install_extra', 'additional_floor'):
            value = getattr(self, name)
            if value is None and name in ('archive_bytes', 'expanded_bytes'): continue
            integer(value, name)
        if type(self.verified) is not bool: raise StorageError('Invalid size verification state.')
        if self.known:
            integer(self.cache_required + self.install_required + self.additional_floor, 'combined size')

    @property
    def known(self):
        return self.verified and self.archive_bytes is not None and self.expanded_bytes is not None

    @property
    def cache_required(self):
        return None if self.archive_bytes is None else self.archive_bytes + self.cache_extra

    @property
    def install_margin(self):
        return None if self.expanded_bytes is None else (self.expanded_bytes + 1) // 2

    @property
    def install_required(self):
        return None if self.expanded_bytes is None else self.expanded_bytes + self.install_margin + self.install_extra


@dataclass(frozen=True)
class VolumeBudget:
    volume_id: str
    label: str
    root: str
    roles: tuple
    free: int
    required: int | None
    other: int
    floor: int

    @property
    def fits(self):
        return None if self.required is None else self.required + self.other + self.floor <= self.free


@dataclass(frozen=True)
class CapacityQuote:
    volumes: tuple
    cache_path: str
    install_path: str

    @property
    def fits(self):
        if any(v.fits is None for v in self.volumes): return None
        return all(v.fits for v in self.volumes)


@dataclass(frozen=True)
class ReservationToken:
    job_id: str
    generation: int
    nonce: str


def initial_state():
    return {'version': 2, 'registrations': [], 'default_install': None, 'jobs': {}}


def validate_state(state):
    """Fail closed on corrupt/incompatible accounting; never silently reset it."""
    try:
        if not isinstance(state, dict) or set(state) != {'version', 'registrations', 'default_install', 'jobs'} or type(state['version']) is not int or state['version'] != 2:
            raise ValueError()
        if not isinstance(state['registrations'], list) or not isinstance(state['jobs'], dict): raise ValueError()
        ids = set(); volumes = set(); cache_count = 0
        for registration in state['registrations']:
            if set(registration) != {'id', 'roles', 'volume_id', 'label', 'last_root'}: raise ValueError()
            identity(registration['id']); text(registration['volume_id'], 'volume identity')
            text(registration['label'], 'label'); root_path(registration['last_root'])
            roles = registration['roles']
            if not isinstance(roles,list) or not roles or any(role not in CHILDREN for role in roles) or len(set(roles))!=len(roles):raise ValueError()
            if registration['id'] in ids or registration['volume_id'] in volumes:raise ValueError()
            volumes.add(registration['volume_id']);ids.add(registration['id']);cache_count += 'cache' in roles
        if cache_count > 1: raise ValueError()
        installs = {r['id'] for r in state['registrations'] if 'install' in r['roles']}
        if (installs and state['default_install'] not in installs) or (not installs and state['default_install'] is not None):
            raise ValueError()
        active = set()
        for key, job in state['jobs'].items():
            if set(job) != {'job_id', 'generation', 'nonce', 'status', 'plan', 'bindings', 'allocated'}: raise ValueError()
            identity(job['job_id']); identity(job['nonce']); integer(job['generation'], 'generation', 1)
            if key != f"{job['job_id']}:{job['generation']}" or job['status'] not in ('active', 'released'): raise ValueError()
            if not isinstance(job['plan'], dict) or set(job['plan']) != set(SizePlan.__dataclass_fields__): raise ValueError()
            plan = SizePlan(**job['plan'])
            if not plan.known or set(job['bindings']) != set(CHILDREN) or set(job['allocated']) != set(CHILDREN): raise ValueError()
            for role, binding in job['bindings'].items():
                if set(binding) != {'registration_id', 'volume_id', 'mount_id', 'root'}: raise ValueError()
                identity(binding['registration_id']); text(binding['volume_id'], 'volume identity')
                text(binding['mount_id'], 'mount identity'); root_path(binding['root'])
                limit = plan.cache_required if role == 'cache' else plan.expanded_bytes + plan.install_extra
                if integer(job['allocated'][role], 'owned allocation') > limit: raise ValueError()
                if job['status'] == 'active':
                    registration = next(r for r in state['registrations'] if r['id'] == binding['registration_id'])
                    if role not in registration['roles'] or registration['volume_id'] != binding['volume_id']: raise ValueError()
            if job['status'] == 'active':
                if job['job_id'] in active: raise ValueError()
                active.add(job['job_id'])
    except (KeyError, TypeError, ValueError, StopIteration, StorageError):
        raise StorageError('Storage state is invalid or unsupported. Preserve it for recovery; downloads are blocked.') from None


class StateStore:
    """Single transactional partition registry and future archive ledger.

    BEGIN IMMEDIATE serializes readers that may mutate, including separate
    processes. SQLite rollback protects both-volume admission on exceptions.
    Production uses the private-file specialization in storage_access.
    """
    def __init__(self, path):
        self.path = str(path)

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    @contextmanager
    def transaction(self):
        connection = None
        try:
            connection = self.connect()
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('CREATE TABLE IF NOT EXISTS storage (id INTEGER PRIMARY KEY CHECK (id=1), data TEXT NOT NULL)')
            row = connection.execute('SELECT data FROM storage WHERE id=1').fetchone()
            raw = row[0] if row else None
            if raw is not None and len(raw) > 4 * 1024 * 1024: raise StorageError('Storage ledger exceeds its supported size; preserve it for recovery.')
            state = json.loads(raw) if raw is not None else initial_state()
            validate_state(state)
            yield state
            validate_state(state)
            encoded = json.dumps(state, separators=(',', ':'), sort_keys=True)
            if len(encoded) > 4 * 1024 * 1024: raise StorageError('Storage ledger is full; preserve it for recovery.')
            if encoded != raw:
                connection.execute('INSERT OR REPLACE INTO storage (id,data) VALUES (1,?)', (encoded,))
            connection.commit()
        except (sqlite3.Error, ValueError) as error:
            raise StorageError('Storage state could not be read or saved. Downloads are blocked.') from error
        finally:
            if connection is not None:
                if connection.in_transaction: connection.rollback()
                connection.close()


class StorageModel:
    enabled = True
    reason = 'Isolated Storage model — drive writes and downloads are not connected.'

    def __init__(self, store, observer):
        self.store = store
        self.observer = observer

    def discover(self):
        try:
            volumes = list(self.observer())
            if any(not isinstance(v, Volume) for v in volumes): raise ValueError()
            return volumes
        except Exception as error:
            raise StorageError('Mounted drives could not be checked. Downloads are blocked.') from error

    @staticmethod
    def resolve(volume_id, volumes, *, managed=False):
        matches = [v for v in volumes if v.volume_id == volume_id]
        if not matches: raise StorageError('This drive is offline. Connect and mount it to continue.')
        if len(matches) != 1: raise StorageError('Drive identity is ambiguous. Downloads are blocked.')
        volume = matches[0]
        if volume.reason: raise StorageError(volume.reason)
        if managed and volume.managed_reason: raise StorageError(volume.managed_reason)
        return volume

    def register(self, observed, role, *, cancelled=lambda:False):
        if role not in CHILDREN or not isinstance(observed, Volume): raise StorageError('Choose a mounted root and Storage role.')
        with self.store.transaction() as state:
            volume = self.resolve(observed.volume_id, self.discover(), managed=role=='cache')
            if volume.stamp != observed.stamp: raise StorageError('The mounted drive changed. Refresh and choose it again.')
            if cancelled(): raise StorageError('Drive registration was canceled.')
            if any(r['volume_id']==volume.volume_id for r in state['registrations']):
                raise StorageError('This partition is already registered. Change its roles in Storage.')
            if role=='cache' and any('cache' in r['roles'] for r in state['registrations']):
                raise StorageError('A download cache is already selected.')
            registration_id = str(uuid4())
            state['registrations'].append({'id': registration_id, 'roles': [role], 'volume_id': volume.volume_id,
                                           'label': volume.label, 'last_root': volume.root})
            if role == 'install' and state['default_install'] is None: state['default_install'] = registration_id
            if cancelled(): raise StorageError('Drive registration was canceled.')
        return registration_id

    @staticmethod
    def registration(state, registration_id, role=None):
        registration = next((r for r in state['registrations'] if r['id'] == registration_id), None)
        if registration is None or (role is not None and role not in registration['roles']):
            raise StorageError('Choose a registered ' + (role or 'storage') + ' drive.')
        return registration

    def add_role(self, registration_id, role):
        if role not in CHILDREN:raise StorageError('Choose a supported storage role.')
        with self.store.transaction() as state:
            registration=self.registration(state,registration_id)
            if role in registration['roles']:raise StorageError('This partition already has this role.')
            if role=='cache' and any('cache' in r['roles'] for r in state['registrations']):
                raise StorageError('Remove the current cache role before choosing another partition.')
            self.resolve(registration['volume_id'],self.discover(),managed=role=='cache')
            registration['roles'].append(role)
            if role=='install' and state['default_install'] is None:state['default_install']=registration_id
        return registration_id

    def remove_role(self, registration_id, role):
        with self.store.transaction() as state:
            registration=self.registration(state,registration_id,role)
            if len(registration['roles'])==1:raise StorageError('Remove the registration to remove its last role.')
            if any(j['status']=='active' and j['bindings'][role]['registration_id']==registration_id for j in state['jobs'].values()):
                raise StorageError('This role has a reserved job. Confirm the job has stopped first.')
            registration['roles'].remove(role)
            if role=='install' and state['default_install']==registration_id:
                state['default_install']=next((r['id'] for r in state['registrations'] if 'install' in r['roles']),None)

    def choices(self):
        with self.store.transaction() as state:
            return {'volumes':self.discover(),'registered':{r['volume_id'] for r in state['registrations']}}

    def set_default(self, registration_id):
        with self.store.transaction() as state:
            self.registration(state, registration_id, 'install')
            state['default_install'] = registration_id

    def remove(self, registration_id):
        with self.store.transaction() as state:
            registration = self.registration(state, registration_id)
            if any(j['status'] == 'active' and any(b['registration_id'] == registration_id for b in j['bindings'].values()) for j in state['jobs'].values()):
                raise StorageError('This drive has a reserved job. Confirm the job has stopped before removing its registration.')
            state['registrations'].remove(registration)
            if state['default_install'] == registration_id:
                state['default_install'] = next((r['id'] for r in state['registrations'] if 'install' in r['roles']), None)

    def snapshot(self):
        with self.store.transaction() as state:
            volumes = self.discover(); rows = []
            for registration in state['registrations']:
                row = dict(registration)
                try:
                    volume = self.resolve(registration['volume_id'], volumes, managed='install' not in registration['roles'])
                    registration.update(last_root=volume.root, label=volume.label)
                    row.update(last_root=volume.root, label=volume.label)
                    row.update(status='ready', reason='', root=volume.root, free=volume.free_bytes, total=volume.total_bytes,
                               mount_id=volume.mount_id, device=volume.device, managed_reason=volume.managed_reason)
                except StorageError as error:
                    row.update(status='offline' if not any(v.volume_id == registration['volume_id'] for v in volumes) else 'unavailable',
                               reason=str(error), root=registration['last_root'], free=None, total=None)
                row['paths'] = {role:str(PurePosixPath(row['root'])/CHILDREN[role]) for role in row['roles']}
                row['path'] = row['paths'].get('install',row['paths'].get('cache'))
                row['default'] = row['id'] == state['default_install']
                row['busy'] = any(j['status'] == 'active' and any(b['registration_id'] == row['id'] for b in j['bindings'].values()) for j in state['jobs'].values())
                rows.append(row)
            return {'registrations': rows, 'default_install': state['default_install'],
                    'active_jobs': sum(j['status'] == 'active' for j in state['jobs'].values())}

    def bindings(self, state, install_id, volumes):
        cache = next((r for r in state['registrations'] if 'cache' in r['roles']), None)
        if cache is None: raise StorageError('Choose download cache storage in Settings before downloading.')
        install = self.registration(state, install_id, 'install')
        return {role: {'registration_id': r['id'], **self.resolve(r['volume_id'], volumes, managed=True).stamp}
                for role,r in (('cache',cache),('install',install))}

    @staticmethod
    def remaining(job):
        plan = SizePlan(**job['plan']); amounts = {}
        for role, budget in (('cache', plan.cache_required), ('install', plan.install_required)):
            volume_id = job['bindings'][role]['volume_id']
            amounts[volume_id] = amounts.get(volume_id, 0) + budget - job['allocated'][role]
        return amounts

    def _quote(self, state, install_id, plan, volumes, current=None):
        bindings = self.bindings(state, install_id, volumes)
        if current and current['bindings'] != bindings: raise StorageError('A reserved mount changed. Stop the job and review recovery before continuing.')
        groups = {}
        for role, binding in bindings.items():
            groups.setdefault(binding['volume_id'], []).append(role)
        rows = []
        for volume_id, roles in groups.items():
            volume = self.resolve(volume_id, volumes); other = 0; floor = plan.additional_floor
            for job in state['jobs'].values():
                if job['status'] != 'active': continue
                amounts = self.remaining(job)
                if volume_id not in amounts: continue
                floor = max(floor, job['plan']['additional_floor'])
                if job is not current: other += amounts[volume_id]
            required = None
            if plan.known:
                required = sum(plan.cache_required if role == 'cache' else plan.install_required for role in roles)
                if current: required -= sum(current['allocated'][role] for role in roles)
            rows.append(VolumeBudget(volume_id, volume.label, volume.root, tuple(roles), volume.free_bytes, required, other, floor))
        quote = CapacityQuote(tuple(rows), str(PurePosixPath(bindings['cache']['root']) / CHILDREN['cache']),
                              str(PurePosixPath(bindings['install']['root']) / CHILDREN['install']))
        return quote, bindings

    def quote(self, install_id, plan):
        if not isinstance(plan, SizePlan): raise StorageError('Inspect the archive and expanded sizes first.')
        with self.store.transaction() as state:
            return self._quote(state, install_id, plan, self.discover())[0]

    @staticmethod
    def require_fit(quote):
        if quote.fits is None: raise StorageError('Archive and expanded size must be verified before download or extraction.')
        if not quote.fits: raise StorageError('Not enough available space for both download and extraction, including other reserved jobs.')

    def reserve(self, job_id, generation, install_id, plan):
        identity(job_id); integer(generation, 'generation', 1)
        if not isinstance(plan, SizePlan): raise StorageError('Inspect sizes before downloading.')
        key = f'{job_id}:{generation}'
        with self.store.transaction() as state:
            previous = state['jobs'].get(key)
            if previous:
                if previous['status'] != 'active' or previous['plan'] != asdict(plan) or previous['bindings']['install']['registration_id'] != install_id:
                    raise StorageError('This job generation was already used with another request or released.')
                quote, _ = self._quote(state, install_id, plan, self.discover(), previous)
                self.require_fit(quote)
                return ReservationToken(job_id, generation, previous['nonce'])
            if any(j['job_id'] == job_id and j['status'] == 'active' for j in state['jobs'].values()):
                raise StorageError('This job already owns an active reservation.')
            quote, bindings = self._quote(state, install_id, plan, self.discover())
            self.require_fit(quote)
            token = ReservationToken(job_id, generation, str(uuid4()))
            state['jobs'][key] = {**asdict(token), 'status': 'active', 'plan': asdict(plan),
                                  'bindings': bindings, 'allocated': {'cache': 0, 'install': 0}}
        return token

    @staticmethod
    def job(state, token):
        if not isinstance(token, ReservationToken): raise StorageError('Invalid reservation token.')
        job = state['jobs'].get(f'{token.job_id}:{token.generation}')
        if job is None or job['nonce'] != token.nonce or job['status'] != 'active':
            raise StorageError('This reservation is stale or released.')
        return job

    def revalidate(self, token, phase):
        if phase not in ('stage', 'start', 'resume', 'extraction', 'commit'): raise StorageError('Unknown storage checkpoint.')
        with self.store.transaction() as state:
            job = self.job(state, token)
            quote, _ = self._quote(state, job['bindings']['install']['registration_id'], SizePlan(**job['plan']), self.discover(), job)
            self.require_fit(quote)
            return quote

    def reconcile(self, token, owned_cache_allocation, owned_install_allocation):
        """Trusted adapter boundary: measured job-owned blocks on bound mounts.

        Not a scanner. The adapter must establish ownership/provenance, de-duplicate
        hard links and exclude sparse logical bytes. Never feed engine progress.
        Current production app has no caller; fixtures inject explicit measures.
        """
        with self.store.transaction() as state:
            job = self.job(state, token); plan = SizePlan(**job['plan'])
            self._quote(state, job['bindings']['install']['registration_id'], plan, self.discover(), job)
            for role, value, limit in (('cache', owned_cache_allocation, plan.cache_required),
                                       ('install', owned_install_allocation, plan.expanded_bytes + plan.install_extra)):
                if integer(value, 'measured owned allocation') > limit:
                    raise StorageError('Measured allocation exceeds this job footprint. Inspect the manifest again.')
                job['allocated'][role] = value
            # Save the accurate allocation even when a later revalidation would
            # fail for free-space loss. Checkpoints still block further I/O.

    def release(self, token, *, confirmed_stopped=False):
        if confirmed_stopped is not True: raise StorageError('Uncertain stop: the job keeps its space reservation.')
        with self.store.transaction() as state:
            self.job(state, token)['status'] = 'released'


class UnavailableStorage:
    enabled = False
    reason = 'Storage setup is not connected to drive access yet. Downloads remain unavailable.'

    def discover(self): return []
    def snapshot(self): return {'registrations': [], 'default_install': None, 'active_jobs': 0}
    def register(self, *args, **kwargs): raise StorageError(self.reason)
    remove = set_default = quote = reserve = revalidate = reconcile = release = register
