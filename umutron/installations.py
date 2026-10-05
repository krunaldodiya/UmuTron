"""Persistent installer workflow; completion requires explicit executable confirmation."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID
from .launcher import ACTIVE, defaults, build_command, pid_identity
from .runner_selection import AUTOMATIC, parse_release
from .installer_identity import is_installer_executable, matching_installer_attempt


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
        attempted_executable=str(setup.resolve())
        context=defaults(candidate,self.library.root)
        previous=self.status(candidate).get('proton')
        # Resume the resolved installer build when the user has not chosen a new
        # override. Explicit Use default deliberately opts out of a legacy pin.
        selected=candidate.get('launch',{}).get('proton','')
        resume_policy=not selected or (selected in AUTOMATIC and selected==config.get('proton'))
        if resume_policy and previous and previous not in AUTOMATIC and not parse_release(previous):
            context['proton']=previous
        context['prefix']=config.get('prefix') or context['prefix']
        launch=deepcopy(candidate);launch.update(executable=str(setup),working_dir=str(setup.parent),launch={**context,'arguments':[]})
        config.update(mode='installer',installer=str(setup),prefix=context['prefix'],proton=context['proton'],confirmed=False)
        candidate['installation']=config
        def persist(state,env):
            candidate['installation']['session_id']=state['session_id']
            candidate['installer_attempt']={'session_id':state['session_id'],'executable':attempted_executable}
            self.library.save(candidate)
        self.launcher.start(launch,operation='installer',before_start=persist)
        return next(g for g in self.library.games() if g['id']==game['id'])

    def _bind_saved_attempt(self,candidate):
        """Pin the saved session before accepting edits to an unstarted draft."""
        previous=next((g for g in self.library.games() if g['id']==candidate['id']),{})
        config=candidate.get('installation',{});saved=previous.get('installation',{})
        if not config.get('session_id') or config['session_id']!=saved.get('session_id'):return
        attempt=matching_installer_attempt(previous)
        if attempt:
            candidate['installer_attempt']=deepcopy(attempt)
        else:
            # Legacy journals have no executable identity. Use the previously
            # saved selection, never the new draft, on this explicit user save.
            original=Path(saved.get('installer',''))
            if not original.is_absolute():raise ValueError('The completed installer could not be identified. Review Setup first.')
            candidate['installer_attempt']={'session_id':config['session_id'],'executable':str(original.resolve())}

    def validated_executable(self,game):
        """Validate explicit executable confirmation without changing saved data."""
        if self.launcher.active():raise RuntimeError('Finish the current game or installer before confirming files.')
        candidate=deepcopy(game);config=dict(candidate.get('installation',{}));status=self.status(candidate)
        executable=Path(candidate['executable'])
        if not candidate['executable'] or not executable.is_absolute() or not executable.is_file():raise ValueError('Select the installed game executable.')
        if config.get('mode')=='installer':
            if not config.get('session_id'):raise ValueError('Run the installer first, or choose Already installed.')
            self._bind_saved_attempt(candidate)
            if is_installer_executable(candidate):raise ValueError('Select the game executable, not its setup installer.')
            tool=status.get('proton') or config.get('proton')
            if tool in ('UMU-Latest','GE-Latest'):
                raise ValueError('The installer runner version could not be resolved. Choose an installed Proton version and retry setup in the same prefix.')
            config.update(proton=tool,confirmed=True)
            candidate['installation']=config
            # Keep installer prefix/runtime continuity even if app defaults changed.
            candidate['launch']={**candidate.get('launch',{}),'prefix':config['prefix'],'proton':tool}
        build_command(candidate,self.library.root)
        return candidate

    def prepare_setup_save(self,game):
        """An explicit Save may confirm a completed install, never infer completion."""
        if self.launcher.active():raise RuntimeError('Finish the current game or installer before saving setup.')
        candidate=deepcopy(game);config=candidate.get('installation',{})
        if config.get('mode')=='installer':
            previous=next((g for g in self.library.games() if g['id']==candidate['id']),{})
            if candidate['executable']!=previous.get('executable',''):config['confirmed']=False
            if not config.get('confirmed') or config.get('installer')!=previous.get('installation',{}).get('installer'):
                self._bind_saved_attempt(candidate)
            if config.get('confirmed') and is_installer_executable(candidate):raise ValueError('Select the game executable, not its setup installer.')
            if candidate['executable'] and not config.get('confirmed'):
                status=self.status(candidate)
                if status.get('operation')=='installer' and status.get('state')=='Finished' and type(status.get('code')) is int and status['code']==0:
                    return self.validated_executable(candidate)
        return candidate

    def confirm(self,game):
        candidate=self.validated_executable(game)
        return self.library.save_setup(candidate)
