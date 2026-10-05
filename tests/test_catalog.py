import json
from pathlib import Path
import tempfile
import unittest

from game_library.library import Library


class CatalogContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def provider(self, rows):
        from game_library.catalog import IGDBCatalog
        calls = []
        def query(endpoint, body):
            calls.append((endpoint, body))
            if endpoint == 'genres': return [{'id':5,'name':'Shooter'},{'id':12,'name':'Role-playing (RPG)'}]
            return rows
        return IGDBCatalog(query), calls

    def test_provider_search_paging_uses_igdb_taxonomy_and_escaped_query(self):
        provider, calls = self.provider([{'id':i,'name':f'Game {i}'} for i in range(1,26)])
        page = provider.browse('A"; limit 500;', 5, 2)
        self.assertEqual(len(page['items']),24); self.assertTrue(page['has_next'])
        query = calls[-1][1]
        self.assertIn('offset 24;',query); self.assertIn('limit 25;',query)
        self.assertIn('genres = 5',query); self.assertIn('search '+json.dumps('A"; limit 500;')+';',query)
        self.assertNotIn('category1',query)
        with self.assertRaises(ValueError):provider.browse('a',True,1)

    def test_external_steam_mapping_requires_current_source_and_unambiguous_uid(self):
        from game_library.catalog import steam_id
        row={'game':10,'external_game_source':{'id':99,'name':'Steam'},'uid':'620','url':'https://store.steampowered.com/app/620/Portal_2/'}
        self.assertEqual(steam_id([row],10),620)
        self.assertIsNone(steam_id([row,{**row,'uid':'400'}],10))
        self.assertIsNone(steam_id([{**row,'game':11}],10))
        self.assertIsNone(steam_id([{'game':10,'category':1,'uid':'620'}],10))

    def test_add_is_idempotent_and_preserves_saved_setup_and_legacy_records(self):
        from game_library.catalog import add_item
        library=Library(self.root/'library')
        manual=library.new_game();manual.update(title='Legacy',executable='/games/old.exe');library.save(manual)
        item={'id':10,'name':'Catalog game','genres':[],'images':{}}
        added,created=add_item(library,item,{})
        self.assertTrue(created);added['working_dir']='/games/specific';library.save(added)
        again,created=add_item(library,{**item,'name':'New provider title'},{})
        self.assertFalse(created);self.assertEqual(added,again)
        self.assertEqual(len(library.games()),2);self.assertEqual(library.games()[0],manual)

    def test_cached_page_survives_provider_failure_and_malformed_cache_is_rejected(self):
        from game_library.catalog import CatalogService
        provider,_=self.provider([{'id':10,'name':'Cached game'}])
        service=CatalogService(provider,self.root/'cache')
        self.assertFalse(service.browse('',None,1)['cached'])
        provider.query=lambda *_: (_ for _ in ()).throw(OSError('offline'))
        page=service.browse('',None,1)
        self.assertTrue(page['cached']);self.assertEqual(page['items'][0]['id'],10)
        for file in (self.root/'cache').glob('*.json'): file.write_text('{')
        with self.assertRaises(Exception):service.browse('',None,1)


if __name__=='__main__':unittest.main()
