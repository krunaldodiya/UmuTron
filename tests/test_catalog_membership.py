from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from game_library.catalog import add_item,members,related_members,needs_membership_lookup
from game_library.library import Library


class CatalogMembershipTests(unittest.TestCase):
    def setUp(self):
        self.temp= tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.library=Library(Path(self.temp.name));self.item={'id':334647,'name':'Grand Theft Auto V Enhanced','steam_app_id':3240220}
        self.game=self.library.new_game();self.game.update(title=self.item['name'],metadata_source={'provider':'steam','id':3240220},metadata_app_id=3240220,executable='/inert/GTA5.exe',working_dir='/inert',launch={'arguments':['preserve']})
        self.library.save(self.game)

    def test_shared_steam_is_related_not_membership_and_explicit_add_preserves_legacy(self):
        self.assertEqual(members(self.library,self.item),[])
        self.assertEqual(related_members(self.library,self.item),[self.game])
        game,created=add_item(self.library,self.item,{})
        self.assertTrue(created);self.assertNotEqual(game['id'],self.game['id'])
        self.assertEqual(game['metadata_source'],{'provider':'igdb','id':self.item['id']})
        self.assertEqual(next(g for g in self.library.games() if g['id']==self.game['id']),self.game)
        before=self.library.path.read_bytes()
        again,created=add_item(self.library,{**self.item,'name':'New catalog title'}, {})
        self.assertFalse(created);self.assertEqual(again,game)
        self.assertEqual(self.library.path.read_bytes(),before)

    def test_bundle_and_component_share_steam_but_remain_distinct_tracked_entries(self):
        bundle,created=add_item(self.library,{**self.item,'game_type':'Bundle'},{});self.assertTrue(created)
        component={**self.item,'id':334254,'game_type':'Expanded Game'}
        self.assertEqual(members(self.library,component),[])
        self.assertEqual({g['id'] for g in related_members(self.library,component)},{self.game['id'],bundle['id']})
        game,created=add_item(self.library,component,{});self.assertTrue(created)
        self.assertNotEqual(game['id'],bundle['id'])
        self.assertEqual(members(self.library,self.item),[bundle]);self.assertEqual(members(self.library,component),[game])
        self.assertEqual(len(self.library.games()),3)

    def test_legacy_edition_missing_mapping_and_title_alone_never_match(self):
        for steam in (271590,None):
            self.assertEqual(members(self.library,{**self.item,'steam_app_id':steam}),[])
            self.assertEqual(related_members(self.library,{**self.item,'steam_app_id':steam}),[])
        game=deepcopy(self.game);game['metadata_source']={};game['metadata_app_id']=None;self.library.save(game)
        self.assertEqual(related_members(self.library,self.item),[])

    def test_exact_igdb_identity_survives_missing_or_changed_steam_mapping(self):
        self.game.update(metadata_source={'provider':'igdb','id':334647},metadata_app_id=None);self.library.save(self.game)
        for steam in (None,271590,3240220):
            item={**self.item,'steam_app_id':steam}
            self.assertEqual(members(self.library,item),[self.game]);self.assertEqual(related_members(self.library,item),[])
            before=self.library.path.read_bytes();game,created=add_item(self.library,item,{})
            self.assertFalse(created);self.assertEqual(game,self.game);self.assertEqual(self.library.path.read_bytes(),before)

    def test_legacy_steam_metadata_and_conflicting_source(self):
        self.game['metadata_source']={};self.library.save(self.game)
        self.assertEqual(related_members(self.library,self.item),[self.game]);self.assertEqual(members(self.library,self.item),[])
        self.game['metadata_source']={'provider':'steam','id':271590};self.library.save(self.game)
        self.assertEqual(related_members(self.library,self.item),[])

    def test_multiple_exact_igdb_copies_block_add_without_modification(self):
        self.game.update(metadata_source={'provider':'igdb','id':334647});self.library.save(self.game)
        duplicate=deepcopy(self.game);duplicate['id']=self.library.new_game()['id'];self.library.save(duplicate)
        before=self.library.path.read_bytes();self.assertEqual(len(members(self.library,self.item)),2)
        with self.assertRaisesRegex(ValueError,'Multiple saved copies'):add_item(self.library,self.item,{})
        self.assertEqual(self.library.path.read_bytes(),before)

    def test_multiple_related_steam_copies_do_not_claim_exact_membership(self):
        duplicate=deepcopy(self.game);duplicate['id']=self.library.new_game()['id'];self.library.save(duplicate)
        self.assertEqual(members(self.library,self.item),[]);self.assertEqual(len(related_members(self.library,self.item)),2)
        game,created=add_item(self.library,self.item,{})
        self.assertTrue(created);self.assertEqual(members(self.library,self.item),[game])
        self.assertEqual(len(related_members(self.library,self.item)),2)

    def test_title_is_only_a_bounded_related_lookup_hint(self):
        item={**self.item,'steam_app_id':None}
        self.assertTrue(needs_membership_lookup(self.library,item));self.assertEqual(members(self.library,item),[])
        self.assertFalse(needs_membership_lookup(self.library,{**item,'name':'Different title'}))
        self.assertFalse(needs_membership_lookup(self.library,self.item))
        self.game.update(metadata_source={'provider':'igdb','id':334647});self.library.save(self.game)
        self.assertFalse(needs_membership_lookup(self.library,item))

    def test_concurrent_same_library_add_creates_only_one_exact_record(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:add_item(self.library,self.item,{}),range(16)))
        self.assertEqual(sum(created for _,created in results),1)
        self.assertEqual(len({game['id'] for game,_ in results}),1)
        self.assertEqual(len(self.library.games()),2)
        self.assertEqual(next(g for g in self.library.games() if g['id']==self.game['id']),self.game)
