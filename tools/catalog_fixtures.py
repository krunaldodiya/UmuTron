"""Fictional IGDB-shaped catalog, with no network or credentials."""
class FixtureCatalog:
    def __init__(self):self.offline=False;self.calls=[]
    def genres(self):return [{'id':5,'name':'Shooter'},{'id':12,'name':'Role-playing (RPG)'}]
    def browse(self,query='',genre=None,page=1):
        if self.offline:raise OSError('Fixture provider offline')
        self.calls.append((query,genre,page))
        return {'items':[self.detail(i) for i in range((page-1)*24+1,page*24+1)],'page':page,'has_next':page<3}
    def detail(self,game_id):
        if self.offline:raise OSError('Fixture provider offline')
        titles=('Nebula Drift','Echoes of the Valley','Crimson Circuit')
        return {'id':game_id,'name':titles[(game_id-1)%3]+f' {game_id:02}',
                'description':'A fictional catalog title for testing browsing, artwork, navigation and explicit library membership. No game is downloaded or launched.',
                'release_date':'2026-09-15','developers':'Fixture Studio','genres':[{'id':5,'name':'Shooter'}],
                'images':{'portrait':f'https://images.igdb.com/igdb/image/upload/t_cover_big/fixture{(game_id-1)%3}.jpg',
                          'hero':f'https://images.igdb.com/igdb/image/upload/t_screenshot_big/fixture{(game_id-1)%3}.jpg'}}

