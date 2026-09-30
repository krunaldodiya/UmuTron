"""Explicit, backed-up sync to a selected native Steam account."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4
import zlib
from . import vdf
from .library import atomic_write, digest


def steam_running():
    # Conservative: refuse writes if a client or helper belonging to this user lives.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            if proc.stat().st_uid != os.getuid(): continue
            name=(proc/'comm').read_text().strip().lower()
            if name in ('steam','steamwebhelper','steam.sh'): return True
        except (FileNotFoundError,ProcessLookupError,PermissionError): continue
    return False


def discover_accounts():
    roots=[Path.home()/'.local/share/Steam',Path.home()/'.steam/steam']
    found=set()
    for root in roots:
        userdata=root/'userdata'
        if userdata.is_dir():
            for account in userdata.iterdir():
                if account.name.isdigit() and (account/'config').is_dir(): found.add(account.resolve())
    return sorted(found)


def _read(path):
    if path.is_symlink(): raise ValueError('Refusing to replace a symbolic link: '+path.name)
    if not path.exists(): return None
    if path.stat().st_size>32*1024*1024: raise ValueError('Steam file is too large.')
    return path.read_bytes()


def _target(account, relative):
    if relative!='config/shortcuts.vdf' and not re.fullmatch(r'config/grid/[0-9]+(?:p|_hero|_logo|_icon)?\.(png|jpg)',relative):
        raise ValueError('Invalid Steam output path.')
    result=account/relative
    if not result.resolve().is_relative_to(account.resolve()): raise ValueError('Steam path escapes the account folder.')
    return result


def _encode(data): return None if data is None else base64.b64encode(data).decode('ascii')
def _decode(data): return None if data is None else base64.b64decode(data,validate=True)


class SteamSync:
    def __init__(self, library, running=steam_running):
        self.library=library; self.running=running
        self.backups=library.root/'steam-backups'

    def preview(self, game, account):
        if self.running(): raise RuntimeError('Exit Steam completely, then preview again. No files were changed.')
        account=Path(account).resolve()
        if not (account/'config').is_dir(): raise ValueError('Select a valid Steam userdata account folder.')
        executable=Path(game['executable']).expanduser()
        if not executable.is_absolute() or not executable.is_file(): raise ValueError('Relink the missing game executable before syncing.')
        if '"' in str(executable): raise ValueError('Executable paths containing double quotes are not supported.')
        work=game['working_dir'] or str(executable.parent)
        if not Path(work).is_absolute() or not Path(work).is_dir() or '"' in work:
            raise ValueError('Choose an existing absolute working directory without double quotes.')
        relative='config/shortcuts.vdf'
        original=_read(_target(account,relative))
        tree=vdf.loads(original) if original is not None else {'shortcuts':(0,{})}
        if set(tree)!={'shortcuts'} or tree['shortcuts'][0]!=0: raise ValueError('Unrecognized Steam shortcuts structure.')
        entries=tree['shortcuts'][1]
        if any(kind!=0 or not key.isdigit() for key,(kind,_) in entries.items()): raise ValueError('Invalid shortcut entries.')
        mapping=game.get('sync')
        ids=[vdf.value(entry,'appid',None) for _,entry in entries.values()]
        if any(type(i) is not int for i in ids) or len(set(ids))!=len(ids): raise ValueError('Steam shortcut IDs are missing or duplicated.')
        matches=[]
        if mapping and mapping['account']==str(account):
            matches=[key for key,(_,entry) in entries.items() if vdf.value(entry,'appid')==mapping['shortcut_id']]
        if not matches:
            matches=[key for key,(_,entry) in entries.items() if vdf.value(entry,'Exe').strip('"')==str(executable)]
        if len(matches)>1: raise ValueError('Multiple Steam shortcuts match this executable; resolve duplicates in Steam first.')
        for other in self.library.games():
            if other['id']==game['id'] or not other.get('sync'): continue
            if matches and other['sync']['account']==str(account) and other['sync']['shortcut_id']==vdf.value(entries[matches[0]][1],'appid'):
                raise ValueError('This Steam shortcut is already managed by another library entry.')
        adopted=bool(matches) and not (mapping and mapping['account']==str(account))
        quoted='"'+str(executable)+'"'
        if matches:
            key=matches[0]; entry=entries[key][1]; shortcut_id=vdf.value(entry,'appid')
        else:
            key=str(max([int(k) for k in entries]+[-1])+1)
            shortcut_id=mapping['shortcut_id'] if mapping and mapping['account']==str(account) else (zlib.crc32((quoted+game['title']).encode())|0x80000000)
            while shortcut_id in ids or shortcut_id==game.get('metadata_app_id'):
                shortcut_id=((shortcut_id+1)&0xffffffff)|0x80000000
            entry={'appid':vdf.integer(shortcut_id),'AppName':vdf.text(game['title']),
                   'Exe':vdf.text(quoted),'StartDir':vdf.text('"'+work+'"'),'icon':vdf.text(''),
                   'ShortcutPath':vdf.text(''),'LaunchOptions':vdf.text(game['arguments']),
                   'IsHidden':vdf.integer(0),'AllowDesktopConfig':vdf.integer(1),
                   'AllowOverlay':vdf.integer(1),'OpenVR':vdf.integer(0),'Devkit':vdf.integer(0),
                   'DevkitGameID':vdf.text(''),'DevkitOverrideAppID':vdf.integer(0),
                   'LastPlayTime':vdf.integer(0),'FlatpakAppID':vdf.text(''),'tags':(0,{})}
            entries[key]=(0,entry)
        changes=[]
        for field,new in (('AppName',game['title']),('Exe',quoted),('StartDir','"'+work+'"'),('LaunchOptions',game['arguments'])):
            old=vdf.value(entry,field)
            if old!=new: changes.append(f'{field}: {old or "(empty)"} → {new or "(empty)"}')
            vdf.put(entry,field,vdf.text(new))
        files={}
        suffix={'portrait':'p','landscape':'','hero':'_hero','logo':'_logo','icon':'_icon'}
        for kind,name in game['artwork'].items():
            source=self.library.art_dir/name
            data=source.read_bytes()
            output=f'config/grid/{shortcut_id}{suffix[kind]}{source.suffix}'
            files[output]={'before':_read(_target(account,output)),'after':data}
            alternate=output[:-len(source.suffix)]+('.jpg' if source.suffix=='.png' else '.png')
            old=_read(_target(account,alternate))
            if old is not None: files[alternate]={'before':old,'after':None}
            changes.append('Set '+kind+' artwork')
            if kind=='icon': vdf.put(entry,'icon',vdf.text(str(account/output)))
        files[relative]={'before':original,'after':vdf.dumps(tree)}
        files={k:v for k,v in files.items() if v['before']!=v['after']}
        if not matches: changes.insert(0,'Add non-Steam shortcut: '+game['title'])
        if adopted: changes.insert(0,'Update matching existing shortcut (preserve its launch ID).')
        if not changes: changes=['No shortcut field changes; record local metadata as synced.']
        return {'account':str(account),'shortcut_id':shortcut_id,'game_id':game['id'],
                'game_digest':digest(game),'title':game['title'],'changes':changes,'files':files}

    def _check(self, account, files, side):
        if self.running(): raise RuntimeError('Steam is running. Exit Steam before applying changes.')
        for relative,item in files.items():
            if _read(_target(account,relative))!=item[side]:
                raise RuntimeError('Steam files changed after the preview. Preview again before continuing.')

    def apply(self, plan):
        if self.backups.exists() and any(json.loads(p.read_text()).get('state')=='prepared' for p in self.backups.glob('*.json')):
            raise RuntimeError('An interrupted sync needs recovery. Use Undo last sync first.')
        game=next(g for g in self.library.games() if g['id']==plan['game_id'])
        if digest(game)!=plan['game_digest']: raise RuntimeError('Game details changed; preview again.')
        account=Path(plan['account']); self._check(account,plan['files'],'before')
        self.backups.mkdir(exist_ok=True)
        backup=self.backups/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-'+uuid4().hex+'.json')
        journal={k:v for k,v in plan.items() if k!='files'}
        journal['state']='prepared'
        journal['files']={k:{side:_encode(data) for side,data in item.items()} for k,item in plan['files'].items()}
        atomic_write(backup,json.dumps(journal,indent=2).encode())
        completed=[]
        try:
            self._check(account,plan['files'],'before')
            for relative,item in plan['files'].items():
                target=_target(account,relative)
                if self.running(): raise RuntimeError('Steam opened during sync; changes will be rolled back.')
                if _read(target)!=item['before']: raise RuntimeError('A Steam file changed during sync.')
                if item['after'] is None: target.unlink(missing_ok=True)
                else: atomic_write(target,item['after'])
                completed.append(relative)
            self.library.mark_synced(plan['game_id'],account,plan['shortcut_id'])
        except Exception:
            for relative in reversed(completed):
                target=_target(account,relative); before=plan['files'][relative]['before']
                if before is None: target.unlink(missing_ok=True)
                else: atomic_write(target,before)
            journal['state']='rolled_back'; atomic_write(backup,json.dumps(journal,indent=2).encode())
            raise
        journal['state']='applied'; atomic_write(backup,json.dumps(journal,indent=2).encode())
        return backup

    def latest_backup(self):
        if not self.backups.exists(): return None
        for path in sorted(self.backups.glob('*.json'),reverse=True):
            if json.loads(path.read_text()).get('state') in ('applied','prepared'): return path
        return None

    def undo(self, backup):
        if backup is None: raise ValueError('No applied sync to undo.')
        journal=json.loads(Path(backup).read_text())
        if journal['state'] not in ('applied','prepared'): raise ValueError('This sync cannot be undone automatically.')
        account=Path(journal['account'])
        files={k:{side:_decode(data) for side,data in item.items()} for k,item in journal['files'].items()}
        if journal['state']=='prepared':
            if self.running(): raise RuntimeError('Exit Steam before recovering an interrupted sync.')
            for relative,item in files.items():
                current=_read(_target(account,relative))
                if current not in (item['before'],item['after']):
                    raise RuntimeError('Steam files changed since the interrupted sync; recovery was stopped.')
                item['after']=current
        else: self._check(account,files,'after')
        journal['state']='prepared'
        atomic_write(Path(backup),json.dumps(journal,indent=2).encode())
        completed=[]
        try:
            for relative,item in files.items():
                target=_target(account,relative)
                if item['before'] is None: target.unlink(missing_ok=True)
                else: atomic_write(target,item['before'])
                completed.append(relative)
        except Exception:
            for relative in reversed(completed):
                target=_target(account,relative); after=files[relative]['after']
                if after is None: target.unlink(missing_ok=True)
                else: atomic_write(target,after)
            raise
        self.library.mark_unsynced(journal['game_id'])
        journal['state']='undone'; atomic_write(Path(backup),json.dumps(journal,indent=2).encode())
