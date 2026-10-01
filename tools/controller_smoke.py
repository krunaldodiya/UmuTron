"""Real SDL2 virtual-controller fixture; never injects OS keys or runs games."""
import ctypes as C
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from game_library.controller import Controller

class GUID(C.Structure):_fields_=[('data',C.c_uint8*16)]
actions=[];enabled=[True]
c=Controller(actions.append,lambda:enabled[0]);assert c.sdl,c.error
s=c.sdl
for name,args,result in (
    ('SDL_JoystickAttachVirtual',[C.c_int,C.c_int,C.c_int,C.c_int],C.c_int),
    ('SDL_JoystickDetachVirtual',[C.c_int],C.c_int),
    ('SDL_JoystickGetDeviceGUID',[C.c_int],GUID),
    ('SDL_GameControllerAddMapping',[C.c_char_p],C.c_int),
    ('SDL_JoystickOpen',[C.c_int],C.c_void_p),
    ('SDL_JoystickClose',[C.c_void_p],None),
    ('SDL_JoystickSetVirtualButton',[C.c_void_p,C.c_int,C.c_uint8],C.c_int),
    ('SDL_JoystickSetVirtualAxis',[C.c_void_p,C.c_int,C.c_int16],C.c_int),
):
    f=getattr(s,name);f.argtypes=args;f.restype=result
index=s.SDL_JoystickAttachVirtual(1,2,15,0);assert index>=0
joy=None
try:
    guid=bytes(s.SDL_JoystickGetDeviceGUID(index).data).hex()
    mapping=f'{guid},Launcher fixture,a:b0,b:b1,x:b2,start:b6,dpup:b11,dpdown:b12,dpleft:b13,dpright:b14,leftx:a0,lefty:a1,platform:Linux,'
    assert s.SDL_GameControllerAddMapping(mapping.encode())>=0
    joy=s.SDL_JoystickOpen(index);assert joy
    c.handle=s.SDL_GameControllerOpen(index);assert c.handle
    c.name='Launcher fixture'
    def sample(button,value):
        assert s.SDL_JoystickSetVirtualButton(joy,button,value)==0
        c.poll();time.sleep(.01)
    sample(0,1);sample(0,1);assert actions==['select'],actions
    sample(0,0);sample(1,1);assert actions[-1]=='back';sample(1,0)
    enabled[0]=False;sample(2,1);enabled[0]=True;sample(2,1);assert 'play' not in actions
    sample(2,0);sample(2,1);assert actions[-1]=='play';sample(2,0)
    assert s.SDL_JoystickSetVirtualAxis(joy,0,22000)==0;c.poll();assert actions[-1]=='right'
    s.SDL_JoystickSetVirtualAxis(joy,0,0);c.poll()
    print('PASS: SDL2 virtual controller, face-button debounce, stick navigation and background/refocus suppression')
finally:
    if joy:s.SDL_JoystickClose(joy)
    if c.handle:s.SDL_GameControllerClose(c.handle);c.handle=None
    s.SDL_JoystickDetachVirtual(index);c.close()
