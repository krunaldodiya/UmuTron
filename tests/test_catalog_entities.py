from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from game_library.catalog import CatalogService,entity_label,validate_item


class CatalogEntityTests(unittest.TestCase):
    def setUp(self):
        self.item={'id':12,'name':'Same title','game_type':'Bundle','platforms':[{'id':6,'name':'PC (Microsoft Windows)'}]}

    def test_optional_fields_preserve_old_response_compatibility(self):
        item=validate_item({'id':12,'name':'Old cache'})
        self.assertIsNone(item['game_type']);self.assertEqual(item['platforms'],[])
        self.assertEqual(entity_label(item),'Catalog entry')
        self.assertEqual(entity_label(validate_item({**self.item,'game_type':None})),'Catalog entry · PC (Microsoft Windows)')

    def test_label_distinguishes_generic_types_without_title_identity(self):
        item=validate_item(self.item)
        self.assertEqual(entity_label(item),'Bundle · PC (Microsoft Windows)')
        self.assertEqual(entity_label(item,compact=True),'Bundle · PC')
        for value in ('Expanded Game','expanded_game'):
            self.assertEqual(entity_label(validate_item({**self.item,'game_type':value}),True),'Expanded game · PC')
        self.assertEqual(entity_label(validate_item({**self.item,'game_type':'A future type'}),True),'Catalog entry · PC')
        multi=validate_item({**self.item,'platforms':self.item['platforms']+[{'id':3,'name':'Linux'},{'id':14,'name':'Mac'}]})
        self.assertEqual(entity_label(multi,True),'Bundle · PC +2')
        self.assertEqual(entity_label(multi),'Bundle · PC (Microsoft Windows) · Linux · Mac')

    def test_malformed_additive_fields_fail_without_unbounded_text(self):
        for field,value in [('game_type',3),('game_type',False),('game_type','x'*65),('game_type','bad\0text'),('platforms',None),('platforms',{}),('platforms',[self.item['platforms'][0]]*101),('platforms',[None]),('platforms',[{'id':True,'name':'PC'}]),('platforms',[{'id':-1,'name':'PC'}]),('platforms',[{'id':6,'name':' '}]),('platforms',[{'id':6,'name':'x'*201}])]:
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validate_item({**self.item,field:value})

    def test_validated_fields_survive_browse_detail_and_offline_snapshots(self):
        class Provider:
            def __init__(self,item):self.item=item;self.offline=False
            def detail(self,identity):
                if self.offline:raise OSError('Offline fixture')
                return deepcopy(self.item)
            def browse(self,*_):return {'items':[self.detail(12)],'page':1,'has_next':False}
        with tempfile.TemporaryDirectory() as temp:
            item={**self.item,'relationships':{'bundles':[], 'expanded_games':[], 'parent_game':None,'version_parent':None,
                  'bundle_contents':{'items':[{'id':44,'name':'Component'}],'complete':False}}}
            provider=Provider(item);service=CatalogService(provider,Path(temp))
            self.assertEqual(service.browse()['items'][0]['platforms'],self.item['platforms'])
            self.assertEqual(service.detail(12)['game_type'],'Bundle')
            provider.offline=True;offline=CatalogService(provider,Path(temp))
            self.assertEqual(offline.cached_browse()['items'][0]['game_type'],'Bundle')
            detail=offline.detail(12);self.assertTrue(detail['cached'])
            self.assertEqual(entity_label(detail,True),'Bundle · PC')
            self.assertEqual(detail['relationships'],item['relationships'])

    def test_relationships_keep_direction_unknown_empty_and_partial_distinct(self):
        self.assertNotIn('relationships',validate_item(self.item))
        relation={'bundles':[{'id':20,'name':'Containing bundle'}], 'parent_game':{'id':21,'name':'Main game or bundle'},
                  'expanded_games':[{'id':22,'name':'Expanded version'}], 'version_parent':{'id':23,'name':'Edition parent'},
                  'bundle_contents':{'items':[{'id':24,'name':'Component'}],'complete':False},
                  'expanded_from':{'items':[],'complete':True}}
        item=validate_item({**self.item,'relationships':relation})
        self.assertEqual(item['relationships'],relation)
        relation['bundle_contents']['items'][0]['name']='Changed upstream object'
        self.assertEqual(item['relationships']['bundle_contents']['items'][0]['name'],'Component')

    def test_relationships_reject_self_duplicates_oversize_and_invalid_completeness(self):
        target={'id':44,'name':'Component'}
        values=[None,{'bundles':[{'id':12,'name':'Self'}]}, {'bundles':[target,target]},
                {'expanded_games':[target]*101},{'parent_game':{'id':9007199254740992,'name':'Too large'}},
                {'version_parent':{'id':44,'name':'x'*1001}}, {'bundles':[{'id':44,'name':' '}]},
                {'bundle_contents':{'items':[target],'complete':1}}, {'expanded_from':{'items':None,'complete':True}},
                {'bundle_contents':{'items':[{'id':12,'name':'Self'}],'complete':True}}]
        for value in values:
            with self.subTest(value=value),self.assertRaises(ValueError):validate_item({**self.item,'relationships':value})
        with self.assertRaises(ValueError):validate_item({**self.item,'platforms':self.item['platforms']*2})
