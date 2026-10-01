from pathlib import Path
import tempfile
import unittest
from game_library.providers import Credentials, IGDB, SteamGridDB, NoRedirects
from game_library.metadata import allowed, plain


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

    def test_public_default_search_without_credentials_and_provider_switch(self):
        from unittest.mock import patch
        import json
        from game_library import metadata
        def fake(url,limit=0):
            if 'storesearch' in url:return json.dumps({'items':[{'type':'app','id':620,'name':'Portal 2'}]}).encode()
            return json.dumps({'620':{'success':True,'data':{'name':'Portal 2','short_description':'<p>Public description</p>'}}}).encode()
        with patch.object(metadata,'request',side_effect=fake):
            self.assertEqual(metadata.search('Portal')[0]['id'],620)
            self.assertEqual(metadata.search('620')[0]['name'],'Portal 2')
            self.assertEqual(metadata.details(620)['description'],'Public description')
        self.assertFalse(self.credentials.path.exists())
        with self.assertRaisesRegex(ValueError,'Providers'):IGDB(self.credentials).search('Portal')

    def test_hash_qualified_catalogue_artwork(self):
        from unittest.mock import patch
        from game_library import metadata
        import json
        assets={'asset_url_format':'steam/apps/3468650/${FILENAME}?t=123',
                'library_capsule_2x':'coverhash/library_capsule_2x.jpg',
                'library_hero':'herohash/library_hero.jpg'}
        payload={'response':{'store_items':[{'appid':3468650,'success':1,'assets':assets}]}}
        with patch.object(metadata,'request',side_effect=lambda *args:json.dumps(payload).encode()):
            found=metadata.catalogue_artwork(3468650)
            self.assertIn('/coverhash/library_capsule_2x.jpg',found['portrait'])
            self.assertIn('/herohash/library_hero.jpg',found['hero'])
            self.assertNotIn('logo',found)
            assets['library_capsule_2x']='../../evil.jpg'
            self.assertNotIn('portrait',metadata.catalogue_artwork(3468650))
            assets['asset_url_format']='https://evil.example/${FILENAME}'
            self.assertEqual(metadata.catalogue_artwork(3468650),{})

    def test_catalogue_failure_keeps_legacy_artwork_fallback(self):
        from unittest.mock import patch
        from game_library import metadata
        with patch.object(metadata,'details',return_value={'title':'Old game','header_url':''}),patch.object(metadata,'catalogue_artwork',side_effect=ValueError('Unavailable')),patch.object(metadata,'request',return_value=b'image'),patch.object(metadata,'image_extension',return_value='.png'):
            _,art,missing=metadata.fetch_game(620)
            self.assertEqual(set(art),{'portrait','landscape','hero','logo'})
            self.assertEqual(missing,[])
