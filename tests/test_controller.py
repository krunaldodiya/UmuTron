import tempfile
import unittest
from pathlib import Path
from game_library.controller import Controller, Navigation, device_identity


class FakeSdl:
    def __init__(self,path):
        self.path=str(path);self.closed=0;self.refreshed=0;self.attached=1
    def SDL_GameControllerUpdate(self):pass
    def SDL_GameControllerGetAttached(self,handle):return self.attached
    def SDL_GameControllerClose(self,handle):self.closed+=1
    def SDL_GameControllerGetJoystick(self,handle):return 1
    def SDL_JoystickPath(self,joystick):return self.path.encode()
    def SDL_GameControllerGetButton(self,handle,button):return 0
    def SDL_GameControllerGetAxis(self,handle,axis):return 0
    def SDL_NumJoysticks(self):return 0
    def SDL_QuitSubSystem(self,flags):self.refreshed+=1
    def SDL_InitSubSystem(self,flags):return 0
    def SDL_GetError(self):return b''


class ControllerTests(unittest.TestCase):
    def test_face_buttons_once_and_direction_repeat(self):
        nav=Navigation()
        self.assertEqual(nav.sample({'select','right'},now=0),['right','select'])
        self.assertEqual(nav.sample({'select','right'},now=.1),[])
        self.assertEqual(nav.sample({'select','right'},now=.5),['right'])
        nav.sample(set(),now=.6)
        self.assertEqual(nav.sample({'select'},now=.7),['select'])

    def test_background_and_held_buttons_do_not_launch_on_refocus(self):
        nav=Navigation()
        self.assertEqual(nav.sample({'play'},enabled=False,now=0),[])
        self.assertEqual(nav.sample({'play'},enabled=True,now=.2),[])
        nav.sample(set(),now=.3)
        self.assertEqual(nav.sample({'play'},now=.4),['play'])

    def test_replaced_input_node_releases_stale_controller_and_rescans(self):
        with tempfile.TemporaryDirectory() as temp:
            node=Path(temp)/'event21'
            node.write_text('first connection')
            sdl=FakeSdl(node)
            controller=Controller.__new__(Controller)
            controller.dispatch=lambda action:None;controller.enabled=lambda:True;controller.navigation=Navigation()
            controller.sdl=sdl;controller.handle=1;controller.name='Fixture';controller.error=''
            controller.closed=False;controller.last_scan=0;controller.last_health=0
            controller.path=str(node);controller.path_identity=device_identity(node)
            node.unlink();node.write_text('replacement connection')
            controller.poll()
            self.assertEqual(sdl.closed,1)
            self.assertEqual(sdl.refreshed,1)
            self.assertIsNone(controller.handle)
            self.assertIsNone(controller.path_identity)

    def test_unchanged_input_node_keeps_controller_attached(self):
        with tempfile.TemporaryDirectory() as temp:
            node=Path(temp)/'event21'
            node.write_text('connection')
            sdl=FakeSdl(node)
            controller=Controller.__new__(Controller)
            controller.dispatch=lambda action:None;controller.enabled=lambda:True;controller.navigation=Navigation()
            controller.sdl=sdl;controller.handle=1;controller.name='Fixture';controller.error=''
            controller.closed=False;controller.last_scan=0;controller.last_health=0
            controller.path=str(node);controller.path_identity=device_identity(node)
            controller.poll()
            self.assertEqual(sdl.closed,0)
            self.assertEqual(sdl.refreshed,0)
            self.assertEqual(controller.handle,1)

