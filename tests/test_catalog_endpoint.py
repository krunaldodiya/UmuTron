import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest
from unittest.mock import patch

from game_library.catalog import RemoteCatalog, UnconfiguredCatalog, configured_catalog, loopback_request


class CatalogEndpointTests(unittest.TestCase):
    def test_https_default_and_origin_only_endpoint_joining(self):
        calls=[];client=RemoteCatalog('https://catalog.example.test/',transport=lambda url:calls.append(url))
        client.genres();client.browse('A & B',5,2);client.detail(42)
        self.assertEqual(calls,['https://catalog.example.test/v1/genres','https://catalog.example.test/v1/games?q=A+%26+B&genre=5&page=2','https://catalog.example.test/v1/games/42'])
        self.assertFalse(client.development)
        for endpoint in ('http://localhost:3000','http://127.0.0.1:3000','http://[::1]:3000'):
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError):RemoteCatalog(endpoint)

    def test_opt_in_accepts_only_unambiguous_loopback_http(self):
        for endpoint,canonical in [('http://localhost:3000/','http://127.0.0.1:3000'),('http://127.0.0.1:3000','http://127.0.0.1:3000'),('http://[::1]:3000/','http://[::1]:3000')]:
            with self.subTest(endpoint=endpoint):
                client=RemoteCatalog(endpoint,allow_loopback_http=True)
                self.assertEqual(client.base,canonical);self.assertTrue(client.development)
        for endpoint in ('http://example.test','http://localhost.example.test','http://192.168.1.2:3000','http://0.0.0.0:3000','http://127.1:3000','http://2130706433:3000','http://[::ffff:127.0.0.1]:3000','http://[::1%lo]:3000','http://localhost.:3000','file:///etc/passwd','ftp://127.0.0.1'):
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError):RemoteCatalog(endpoint,allow_loopback_http=True)

    def test_path_credentials_invalid_port_query_fragment_and_controls_rejected(self):
        for endpoint in ('https://catalog.example.test/api/v1/catalog','https://catalog.example.test/v1','https://catalog.example.test//','https://user:secret@catalog.example.test','https://@catalog.example.test','http://user@localhost:3000','http://localhost:0','http://localhost:65536','http://localhost:bad','https://catalog.example.test?q=x','https://catalog.example.test/#fragment',' https://catalog.example.test','https://catalog.example.test\n','https://catalog.example.test\x00'):
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError):RemoteCatalog(endpoint,allow_loopback_http=True)
        with self.assertRaises(ValueError):loopback_request('http://localhost:3000/private/file')

    def test_primary_env_precedence_legacy_alias_and_exact_opt_in(self):
        legacy={'UMUTRON_CATALOG_URL':'https://legacy.example.test'}
        self.assertEqual(configured_catalog(legacy).base,'https://legacy.example.test')
        self.assertEqual(configured_catalog({**legacy,'APP_BASE_URL':'https://new.example.test/'}).base,'https://new.example.test')
        for primary in ('','http://remote.example.test','https://new.example.test/api'):
            self.assertIsInstance(configured_catalog({**legacy,'APP_BASE_URL':primary}),UnconfiguredCatalog)
        for flag in (None,'','true','yes','0',' 1 '):
            self.assertIsInstance(configured_catalog({'APP_BASE_URL':'http://localhost:3000','UMUTRON_ALLOW_LOOPBACK_HTTP':flag}),UnconfiguredCatalog)
        self.assertEqual(configured_catalog({'APP_BASE_URL':'http://localhost:3000','UMUTRON_ALLOW_LOOPBACK_HTTP':'1'}).base,'http://127.0.0.1:3000')
        class OnlyEndpointSettings(dict):
            def get(self,key,default=None):
                if key not in ('APP_BASE_URL','UMUTRON_CATALOG_URL','UMUTRON_ALLOW_LOOPBACK_HTTP'):raise AssertionError('Unexpected environment read')
                return super().get(key,default)
        self.assertIsInstance(configured_catalog(OnlyEndpointSettings(APP_BASE_URL='https://catalog.example.test')),RemoteCatalog)


class LoopbackTransportTests(unittest.TestCase):
    def setUp(self):
        self.requests=[];self.response='normal';owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append((self.path,dict(self.headers)))
                if owner.response=='redirect':
                    self.send_response(302);self.send_header('Location','http://127.0.0.1:1/private');self.end_headers();return
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                if owner.response=='oversize':body=b' '* (4*1024*1024+1)
                else:body=json.dumps({'path':self.path}).encode()
                try:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
            def log_message(self,*_):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.client=RemoteCatalog(f'http://localhost:{self.server.server_port}',allow_loopback_http=True)

    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def test_real_loopback_get_bypasses_proxy_and_sends_no_credentials(self):
        with patch.dict(os.environ,{'HTTP_PROXY':'http://127.0.0.1:1','http_proxy':'http://127.0.0.1:1','ALL_PROXY':'http://127.0.0.1:1','NO_PROXY':'','no_proxy':'','TWITCH_CLIENT_SECRET':'fixture-secret-never-send','IGDB_ACCESS_TOKEN':'fixture-token-never-send'}):
            self.client.genres();self.client.browse('Fixture game',None,2);self.client.detail(42)
        self.assertEqual([path for path,_ in self.requests],['/v1/genres','/v1/games?q=Fixture+game&genre=&page=2','/v1/games/42'])
        for _,headers in self.requests:
            names={name.lower() for name in headers}
            self.assertTrue(names.isdisjoint({'authorization','proxy-authorization','cookie','client-id'}))
            self.assertNotIn('fixture-secret',str(headers));self.assertNotIn('fixture-token',str(headers))

    def test_redirect_is_not_followed(self):
        self.response='redirect'
        with self.assertRaisesRegex(ValueError,'redirects'):self.client.genres()
        self.assertEqual(len(self.requests),1)

    def test_response_size_is_bounded(self):
        self.response='oversize'
        with self.assertRaisesRegex(ValueError,'too large'):self.client.genres()


if __name__=='__main__':unittest.main()
