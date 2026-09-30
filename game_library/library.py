"""Local library and portable backups. This module never launches games."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import tempfile
from uuid import UUID, uuid4
import zipfile

ART_KINDS = ('portrait', 'landscape', 'hero', 'logo', 'icon')
TEXT_FIELDS = ('title','executable','working_dir','arguments','description','release_date','developers','publishers','genres')
MAX_IMAGE = 20 * 1024 * 1024
MAX_ARCHIVE = 512 * 1024 * 1024


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def image_extension(data):
    width=height=0
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        if len(data)<33 or data[12:16]!=b'IHDR': raise ValueError('Invalid PNG image.')
        width,height=struct.unpack('>II',data[16:24]); extension='.png'
    elif data.startswith(b'\xff\xd8\xff'):
        extension='.jpg'; pos=2
        while pos+4<=len(data):
            if data[pos]!=255: break
            while pos<len(data) and data[pos]==255: pos+=1
            if pos>=len(data): break
            marker=data[pos]; pos+=1
            if marker in (0xd8,0xd9,0x01) or 0xd0<=marker<=0xd7: continue
            if marker==0xda: break
            if pos+2>len(data): break
            size=struct.unpack('>H',data[pos:pos+2])[0]
            if size<2 or pos+size>len(data): break
            if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf) and size>=7:
                height,width=struct.unpack('>HH',data[pos+3:pos+7]); break
            pos+=size
    else: raise ValueError('Use a PNG or JPEG image.')
    if not width or not height or width>8192 or height>8192 or width*height>32000000:
        raise ValueError('Artwork has invalid or excessive dimensions (maximum 8192 pixels per side, 32 megapixels).')
    return extension


def digest(game):
    content = {k:v for k,v in game.items() if k not in ('sync','launch')}
    return sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def validate_game(game):
    if not isinstance(game, dict): raise ValueError('Invalid game record.')
    source=game.get('metadata_source',{})
    if not isinstance(source,dict) or set(source)-{'provider','id'} or (source and (source.get('provider') not in ('steam','igdb') or type(source.get('id')) is not int or source['id']<=0)):
        raise ValueError('Invalid metadata source.')
    from .launcher import validate_settings
    validate_settings(game.get('launch',{}))
    from .installations import validate_installation
    validate_installation(game.get('installation',{}))
    UUID(game['id'])
    for key in TEXT_FIELDS:
        if not isinstance(game.get(key), str) or len(game[key]) > 100000 or '\x00' in game[key]:
            raise ValueError('Invalid game field: '+key)
    app_id = game.get('metadata_app_id')
    if app_id is not None and (type(app_id) is not int or app_id <= 0):
        raise ValueError('Invalid metadata ID.')
    art = game.get('artwork')
    if not isinstance(art, dict) or set(art)-set(ART_KINDS): raise ValueError('Invalid artwork.')
    for name in art.values():
        if not isinstance(name, str) or not re.fullmatch(r'[a-f0-9]{64}\.(png|jpg)', name):
            raise ValueError('Invalid artwork filename.')
    sync = game.get('sync')
    if sync is not None:
        if not isinstance(sync, dict) or not isinstance(sync.get('account'), str) or type(sync.get('shortcut_id')) is not int or not 0 <= sync['shortcut_id'] <= 0xffffffff or not isinstance(sync.get('digest'),str):
            raise ValueError('Invalid sync record.')


class Library:
    def __init__(self, root=None):
        self.root = Path(root or Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'game-library-launcher')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.art_dir = self.root/'artwork'; self.art_dir.mkdir(exist_ok=True)
        self.path = self.root/'library.json'
        if root is None and not self.path.exists():
            self._migrate_legacy()
        self.data = {'version':1, 'games':[], 'settings':{'theme':'system'}}
        if self.path.exists():
            if self.path.stat().st_size > 20*1024*1024: raise ValueError('Library is too large.')
            self.data = json.loads(self.path.read_text())
            self._validate(self.data)

    def _migrate_legacy(self):
        legacy=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'steam-library-metadata-manager'
        source=legacy/'library.json'
        if not source.is_file(): return
        if source.stat().st_size>20*1024*1024: raise ValueError('Legacy library is too large.')
        data=json.loads(source.read_text()); self._validate(data)
        for name in {n for g in data['games'] for n in g['artwork'].values()}:
            content=(legacy/'artwork'/name).read_bytes()
            if len(content)>MAX_IMAGE or sha256(content).hexdigest()+image_extension(content)!=name: raise ValueError('Legacy artwork is invalid.')
            atomic_write(self.art_dir/name,content)
        atomic_write(self.path,json.dumps(data,indent=2,ensure_ascii=False).encode())

    @staticmethod
    def _validate(data):
        if not isinstance(data,dict) or data.get('version') != 1 or not isinstance(data.get('games'),list) or len(data['games']) > 10000:
            raise ValueError('Unsupported library format.')
        ids=set()
        for game in data['games']:
            validate_game(game)
            if game['id'] in ids: raise ValueError('Duplicate game identity.')
            ids.add(game['id'])
        if not isinstance(data.get('settings'),dict) or data['settings'].get('theme','system') not in ('system','light','dark'):
            raise ValueError('Invalid appearance settings.')
        runner=data['settings'].get('default_proton','')
        if not isinstance(runner,str) or len(runner)>4096 or '\x00' in runner:raise ValueError('Invalid default runner.')

    def _write(self):
        atomic_write(self.path, json.dumps(self.data,indent=2,ensure_ascii=False).encode())

    @staticmethod
    def new_game():
        return dict(id=str(uuid4()), metadata_app_id=None, metadata_source={}, artwork={}, sync=None, launch={}, installation={},
                    **{k:'' for k in TEXT_FIELDS})

    def games(self): return deepcopy(self.data['games'])

    def save(self, game):
        validate_game(game)
        if not game['title'].strip(): raise ValueError('Enter a game title.')
        previous = deepcopy(self.data)
        self.data['games'] = [deepcopy(game) if g['id']==game['id'] else g for g in self.data['games']]
        if not any(g['id']==game['id'] for g in previous['games']): self.data['games'].append(deepcopy(game))
        try: self._write()
        except Exception:
            self.data=previous; raise

    def delete(self, game_id):
        previous=deepcopy(self.data)
        self.data['games']=[g for g in self.data['games'] if g['id']!=game_id]
        try: self._write()
        except Exception:
            self.data=previous; raise

    def set_theme(self, theme):
        if theme not in ('system','light','dark'): raise ValueError('Unknown theme.')
        self.data['settings']['theme']=theme; self._write()

    def set_default_proton(self,value):
        if not isinstance(value,str) or len(value)>4096 or '\x00' in value:raise ValueError('Invalid default runner.')
        self.data['settings']['default_proton']=value;self._write()

    def mark_synced(self, game_id, account, shortcut_id):
        game = next(g for g in self.games() if g['id']==game_id)
        game['sync']={'account':str(account),'shortcut_id':shortcut_id,'digest':digest(game)}
        self.save(game)

    def mark_unsynced(self, game_id):
        for game in self.games():
            if game['id']==game_id:
                if game.get('sync'): game['sync']['digest']=''
                self.save(game); break

    @staticmethod
    def status(game):
        if not game.get('sync'): return 'Not synced'
        return 'Synced' if game['sync']['digest']==digest(game) else 'Changes pending'

    def add_image(self, data):
        if len(data)>MAX_IMAGE: raise ValueError('Artwork exceeds 20 MB.')
        extension=image_extension(data)
        name=sha256(data).hexdigest()+extension
        atomic_write(self.art_dir/name,data)
        return name

    def export_zip(self, destination):
        manifest=deepcopy(self.data)
        manifest['settings']={'theme':self.data['settings'].get('theme','system'),'default_proton':self.data['settings'].get('default_proton','UMU-Latest')}
        for game in manifest['games']: game['sync']=None
        fd,temp=tempfile.mkstemp(suffix='.zip',dir=Path(destination).parent); os.close(fd)
        try:
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('library.json',json.dumps(manifest,indent=2))
                names={n for g in manifest['games'] for n in g['artwork'].values()}
                for name in sorted(names): z.write(self.art_dir/name,'artwork/'+name)
            os.replace(temp,destination)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    def _read_archive(self, archive):
        with zipfile.ZipFile(archive) as z:
            infos=z.infolist()
            if len(infos)>20000 or sum(i.file_size for i in infos)>MAX_ARCHIVE:
                raise ValueError('Backup exceeds safe import limits.')
            names=set()
            for info in infos:
                path=PurePosixPath(info.filename)
                if info.filename in names or path.is_absolute() or '..' in path.parts or '\\' in info.filename or stat.S_ISLNK(info.external_attr>>16):
                    raise ValueError('Unsafe archive entry.')
                names.add(info.filename)
                if info.filename!='library.json' and not re.fullmatch(r'artwork/[a-f0-9]{64}\.(png|jpg)',info.filename):
                    raise ValueError('Unexpected backup entry.')
                limit=20*1024*1024 if info.filename=='library.json' else MAX_IMAGE
                if info.file_size>limit: raise ValueError('Backup entry is too large.')
            data=json.loads(z.read('library.json'))
            self._validate(data)
            art={}
            for name in {n for g in data['games'] for n in g['artwork'].values()}:
                content=z.read('artwork/'+name)
                if sha256(content).hexdigest()+image_extension(content)!=name:
                    raise ValueError('Artwork checksum mismatch.')
                art[name]=content
            return data,art

    def preview_import(self, archive):
        data,_=self._read_archive(archive)
        existing={g['id'] for g in self.games()}
        conflicts=sum(g['id'] in existing for g in data['games'])
        return {'new':len(data['games'])-conflicts, 'conflicts':conflicts,
                'titles':[g['title'] for g in data['games']]}

    def import_zip(self, archive, conflict='keep'):
        if conflict not in ('keep','replace'): raise ValueError('Select a conflict policy.')
        data,art=self._read_archive(archive)
        merged={g['id']:g for g in self.games()}
        for game in data['games']:
            if game['id'] not in merged or conflict=='replace':
                game['sync']=None; merged[game['id']]=game
        for name,content in art.items(): atomic_write(self.art_dir/name,content)
        previous=deepcopy(self.data)
        self.data['games']=list(merged.values())
        self.data['settings']['theme']=data['settings'].get('theme','system')
        self.data['settings']['default_proton']=data['settings'].get('default_proton','UMU-Latest')
        try: self._write()
        except Exception:
            self.data=previous; raise
