import unittest
from game_library.controller import Navigation


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
