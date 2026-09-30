"""Persistent installer workflow; completion requires explicit executable confirmation."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID
from .launcher import ACTIVE, defaults, build_command, pid_identity


def validate_installation(value):
    if not isinstance(value,dict) or set(value)-{'mode','installer','session_id','prefix','proton','confirmed'}:
        raise ValueError('Invalid installation settings.')
    # Legacy shortcut records remain readable; Manage Game maps them to Already installed.
    if value.get('mode','installed') not in ('installed','installer','shortcut'):raise ValueError('Unknown game installation mode.')
    for key in ('installer','session_id','prefix','proton'):
        item=value.get(key,'')
        if not isinstance(item,str) or len(item)>4096 or '\x00' in item:raise ValueError('Invalid installer '+key+'.')
    if value.get('session_id'):UUID(value['session_id'])
    if 'confirmed' in value and type(value['confirmed']) is not bool:raise ValueError('Invalid executable confirmation.')


class Installations:
    def __init__(self,library,launcher):self.library=library;self.launcher=launcher

    def status(self,game):
        config=game.get('installation',{})
        record_path=self.library.root/'installation-sessions'/(game['id']+'.json')
        record={}
        try:
            if record_path.stat().st_size<=500000:
                candidate=json.loads(record_path.read_text())
                if candidate.get('session_id')==config.get('session_id') and candidate.get('game_id')==game['id']:record=candidate
        except (OSError,ValueError):pass
        state=record.get('state','Not started')
        if state in ACTIVE:
            live=self.launcher.current()
            if not self.launcher.active() or live.get('session_id')!=config.get('session_id'):
                state='Interrupted'
            elif state=='Preparing' and pid_identity(record.get('supervisor_pid',0))!=record.get('supervisor_start'):
                state='Preparing'
        phase={'Finished':'Select installed executable','Error':'Failed','Stopped':'Cancelled'}.get(state,state)
        if config.get('confirmed'):phase='Executable confirmed'
        return {**record,'phase':phase,'logs':record.get('logs',[])}

    def start(self,game):
        if self.launcher.active():raise RuntimeError('Another game or installer is active. Finish it first.')
        candidate=deepcopy(game);config=dict(candidate.get('installation',{}))
        setup=Path(config.get('installer',''))
        if not setup.is_absolute() or not setup.is_file():raise ValueError('Choose an existing installer executable.')
        context=defaults(candidate,self.library.root)
        previous=self.status(candidate).get('proton')
        context['proton']=(previous if previous not in (None,'UMU-Latest','GE-Latest') else config.get('proton')) or candidate.get('launch',{}).get('proton') or self.library.data['settings'].get('default_proton') or context['proton']
        if context['proton'] in ('UMU-Latest','GE-Latest') and candidate.get('launch',{}).get('proton') not in (None,'','UMU-Latest','GE-Latest'):context['proton']=candidate['launch']['proton']
        context['prefix']=config.get('prefix') or context['prefix']
        if context['proton'] not in ('UMU-Latest','GE-Latest'):context['proton']=str(Path(context['proton']).resolve())
        launch=deepcopy(candidate);launch.update(executable=str(setup),working_dir=str(setup.parent),launch={**context,'arguments':[]})
        config.update(mode='installer',installer=str(setup),prefix=context['prefix'],proton=context['proton'],confirmed=False)
        candidate['installation']=config
        def persist(state,env):
            candidate['installation']['session_id']=state['session_id']
            self.library.save(candidate)
        self.launcher.start(launch,operation='installer',before_start=persist)
        return next(g for g in self.library.games() if g['id']==game['id'])

    def confirm(self,game):
        if self.launcher.active():raise RuntimeError('Finish the current game or installer before confirming files.')
        candidate=deepcopy(game);config=dict(candidate.get('installation',{}));status=self.status(candidate)
        executable=Path(candidate['executable'])
        if not candidate['executable'] or not executable.is_absolute() or not executable.is_file():raise ValueError('Select the installed game executable.')
        if config.get('mode')=='installer':
            if not config.get('session_id'):raise ValueError('Run the installer first, or choose Already installed.')
            if executable.resolve()==Path(config.get('installer','')).resolve():raise ValueError('Select the game executable, not its setup installer.')
            tool=status.get('proton') or config.get('proton')
            if tool in ('UMU-Latest','GE-Latest'):
                raise ValueError('The installer runner version could not be resolved. Choose an installed Proton version and retry setup in the same prefix.')
            config.update(proton=tool,confirmed=True)
            candidate['installation']=config
            # Keep installer prefix/runtime continuity even if app defaults changed.
            candidate['launch']={**candidate.get('launch',{}),'prefix':config['prefix'],'proton':tool}
        build_command(candidate,self.library.root)
        self.library.save(candidate)
        return candidate
