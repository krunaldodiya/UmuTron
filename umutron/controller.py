"""Optional SDL2 controller navigation; never sends input to other processes."""
import ctypes as C
from ctypes.util import find_library
import time

DIRECTIONS={'left','right','up','down'}
BUTTONS={0:'select',1:'back',2:'play',6:'desktop',9:'pageup',10:'pagedown',11:'up',12:'down',13:'left',14:'right'}


class Navigation:
    """Debounce actions, repeat directions, and discard buttons while unfocused."""
    def __init__(self):self.held=set();self.next_repeat={}
    def sample(self,pressed,enabled=True,now=None):
        now=time.monotonic() if now is None else now
        pressed=set(pressed);actions=[]
        if enabled:
            for action in sorted(pressed):
                if action not in self.held:
                    actions.append(action);self.next_repeat[action]=now+.4
                elif action in DIRECTIONS and now>=self.next_repeat.get(action,now):
                    actions.append(action);self.next_repeat[action]=now+.16
        else:self.next_repeat={a:now+.4 for a in pressed}
        self.held=pressed
        self.next_repeat={a:t for a,t in self.next_repeat.items() if a in pressed}
        return actions


class Controller:
    def __init__(self,dispatch,enabled):
        self.dispatch=dispatch;self.enabled=enabled;self.navigation=Navigation()
        self.sdl=None;self.handle=None;self.name='';self.error='';self.closed=False;self.last_scan=0
        try:
            library=find_library('SDL2-2.0') or find_library('SDL2')
            if not library:raise OSError('SDL2 unavailable; use keyboard or mouse')
            self.sdl=C.CDLL(library)
            signatures={
                'SDL_InitSubSystem':([C.c_uint32],C.c_int),
                'SDL_QuitSubSystem':([C.c_uint32],None),
                'SDL_SetHint':([C.c_char_p,C.c_char_p],C.c_int),
                'SDL_NumJoysticks':([],C.c_int),
                'SDL_IsGameController':([C.c_int],C.c_int),
                'SDL_GameControllerOpen':([C.c_int],C.c_void_p),
                'SDL_GameControllerClose':([C.c_void_p],None),
                'SDL_GameControllerGetAttached':([C.c_void_p],C.c_int),
                'SDL_GameControllerName':([C.c_void_p],C.c_char_p),
                'SDL_GameControllerGetButton':([C.c_void_p,C.c_int],C.c_uint8),
                'SDL_GameControllerGetAxis':([C.c_void_p,C.c_int],C.c_int16),
                'SDL_GameControllerUpdate':([],None),
                'SDL_GetError':([],C.c_char_p),
            }
            for name,(args,result) in signatures.items():
                method=getattr(self.sdl,name);method.argtypes=args;method.restype=result
            # SDL has no video window here; focus gating belongs to the GTK window.
            self.sdl.SDL_SetHint(b'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS',b'1')
            if self.sdl.SDL_InitSubSystem(0x2000)!=0:
                raise OSError((self.sdl.SDL_GetError() or b'SDL initialization failed').decode(errors='replace'))
        except (OSError,AttributeError) as e:self.error=str(e);self.sdl=None

    def poll(self):
        if self.closed:return False
        if not self.sdl:return True
        self.sdl.SDL_GameControllerUpdate()
        if self.handle and not self.sdl.SDL_GameControllerGetAttached(self.handle):
            self.sdl.SDL_GameControllerClose(self.handle);self.handle=None;self.name='';self.navigation=Navigation()
        now=time.monotonic()
        if not self.handle and now-self.last_scan>=1:
            self.last_scan=now
            for index in range(min(32,max(0,self.sdl.SDL_NumJoysticks()))):
                if self.sdl.SDL_IsGameController(index):
                    self.handle=self.sdl.SDL_GameControllerOpen(index)
                    if self.handle:
                        self.name=(self.sdl.SDL_GameControllerName(self.handle) or b'Controller').decode(errors='replace')[:100]
                        break
        pressed=set()
        if self.handle:
            pressed={action for button,action in BUTTONS.items() if self.sdl.SDL_GameControllerGetButton(self.handle,button)}
            x=self.sdl.SDL_GameControllerGetAxis(self.handle,0);y=self.sdl.SDL_GameControllerGetAxis(self.handle,1)
            if abs(x)>16000 or abs(y)>16000:
                pressed.add(('right' if x>0 else 'left') if abs(x)>=abs(y) else ('down' if y>0 else 'up'))
        for action in self.navigation.sample(pressed,self.enabled(),now):self.dispatch(action)
        return True

    def close(self):
        if self.closed:return
        self.closed=True
        if self.sdl:
            if self.handle:self.sdl.SDL_GameControllerClose(self.handle);self.handle=None
            self.sdl.SDL_QuitSubSystem(0x2000)
