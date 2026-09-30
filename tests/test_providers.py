from pathlib import Path
import tempfile
import unittest
from steam_library.providers import Credentials, IGDB, SteamGridDB, NoRedirects
from steam_library.metadata import allowed, plain


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.credentials=Credentials(Path(self.tmp.name))

    def test_missing_credentials_actionable(self):
        with self.assertRaisesRegex(ValueError,'Providers'): IGDB(self.credentials).search('Game')
        with self.assertRaisesRegex(ValueError,'Providers'): SteamGridDB(self.credentials).search('Game')

    def test_credentials_private_and_request_shape(self):
        self.credentials.save({'igdb_client_id':'fixture-client','igdb_client_secret':'fixture-secret'})
        self.assertEqual(self.credentials.path.stat().st_mode & 0o777,0o600)
        calls=[]
        def transport(url,headers=None,data=None):
            calls.append((url,headers,data))
            return {'access_token':'fixture-token','expires_in':3600} if 'oauth2' in url else [{'id':1,'name':'Game'}]
        result=IGDB(self.credentials,transport).search('Game"; limit 500;')
        self.assertEqual(result,[{'id':1,'name':'Game'}])
        self.assertNotIn('fixture-secret',calls[0][0])
        self.assertIn(b'client_secret=fixture-secret',calls[0][2])
        self.assertIn(b'Game\\"; limit 500;',calls[1][2])

    def test_sgdb_static_artwork_filter_and_bearer_header(self):
        self.credentials.save({'steamgriddb_key':'fixture-key'})
        calls=[]
        def transport(url,headers=None,data=None):
            calls.append((url,headers))
            return {'success':True,'data':[{'id':1,'url':'https://cdn2.steamgriddb.com/test.png','mime':'image/png','author':{'name':'Artist'}}]}
        result=SteamGridDB(self.credentials,transport).artwork(10,'portrait')
        self.assertEqual(result[0]['author'],'Artist')
        self.assertIn('dimensions=600x900',calls[0][0])
        self.assertEqual(calls[0][1]['Authorization'],'Bearer fixture-key')

    def test_download_boundary_rejects_untrusted_hosts(self):
        for url in ('file:///etc/passwd','https://evil.example/pic.png','http://images.igdb.com/a.jpg','https://store.steampowered.com@evil.example/a'):
            with self.subTest(url=url),self.assertRaises(ValueError): allowed(url)
        self.assertEqual(plain('<p>Game &amp; story</p>'),'Game & story')

    def test_authenticated_redirect_not_followed(self):
        with self.assertRaises(ValueError): NoRedirects().redirect_request(None,None,302,'',{},'https://example.com')
