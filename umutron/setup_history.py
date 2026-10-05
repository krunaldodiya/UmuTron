"""Successful local setup chronology, separate from observed play history."""
from copy import deepcopy
import time
from .setup_state import setup_state


def validate_timestamp(game):
    if 'setup_completed_at' in game:
        value=game['setup_completed_at']
        if type(value) is not int or not 0<value<=253402300799:
            raise ValueError('Invalid setup completion timestamp.')


def completed(previous,game):
    """Stamp an explicit ready transition; reopening/saving old setups adds no date."""
    candidate=deepcopy(game)
    if previous and 'setup_completed_at' in previous:
        candidate['setup_completed_at']=previous['setup_completed_at']
    else:
        candidate.pop('setup_completed_at',None)
    def identity(record):
        config=record.get('installation',{})
        return (record.get('executable',''),record.get('working_dir',''),config.get('mode','installed'),
                config.get('session_id',''),config.get('confirmed',False))
    if setup_state(candidate)['ready'] and (not previous or not setup_state(previous)['ready'] or identity(previous)!=identity(candidate)):
        candidate['setup_completed_at']=int(time.time())
    return candidate


def groups(library):
    """True dated setups first; legacy configured records have no invented order."""
    dated=[];undated=[]
    for game in library.games():
        config=game.get('installation',{})
        if game.get('setup_completed_at'):
            dated.append(game)
        elif game.get('executable') and (config.get('mode')!='installer' or (config.get('confirmed') and config.get('session_id'))):
            undated.append(game)
    tie=lambda game:(game['title'].casefold(),game['id'])
    return sorted(dated,key=lambda game:(-game['setup_completed_at'],*tie(game))),sorted(undated,key=tie)
