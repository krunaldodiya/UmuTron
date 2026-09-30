"""Optional provider adapters. Credentials never enter the library or ZIPs."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .library import atomic_write, MAX_IMAGE, image_extension
from . import metadata


class Credentials:
    FIELDS=('igdb_client_id','igdb_client_secret','steamgriddb_key')
    def __init__(self,root=None):
        self.root=Path(root or Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'game-library-launcher')
        self.path=self.root/'providers.json'
        if root is None and not self.path.exists():
            legacy=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'steam-library-metadata-manager/providers.json'
            if legacy.is_file():self.save(json.loads(legacy.read_text()))
    def load(self):
        if not self.path.exists(): return {k:'' for k in self.FIELDS}
        data=json.loads(self.path.read_text())
        return {k:str(data.get(k,'')) for k in self.FIELDS}
    def save(self,data):
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        atomic_write(self.path,json.dumps({k:data.get(k,'').strip() for k in self.FIELDS}).encode())
        self.path.chmod(0o600)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Provider redirected an authenticated request; it was not followed.')


def api_request(url,headers=None,data=None):
    # Endpoint values are created by adapters, never accepted from imported metadata.
    request=Request(url,headers={'User-Agent':'GameLibraryLauncher/0.2',**(headers or {})},data=data)
    try:
        with build_opener(NoRedirects).open(request,timeout=20) as response:
            body=response.read(4*1024*1024+1)
        if len(body)>4*1024*1024: raise ValueError('Provider response is too large.')
        return json.loads(body)
    except HTTPError as error:
        reason={401:'Check your provider credentials.',403:'Access was denied by the provider.',429:'Rate limit reached. Please try again later.'}.get(error.code,'Please try again later.')
        raise ValueError(f'Provider returned HTTP {error.code}. {reason}') from None


class IGDB:
    def __init__(self,credentials,transport=api_request):
        self.credentials=credentials; self.transport=transport
        self.token=None; self.expires=0; self.last=0
    def _query(self,query):
        settings=self.credentials.load(); client=settings['igdb_client_id']; secret=settings['igdb_client_secret']
        if not client or not secret: raise ValueError('Add your IGDB/Twitch client ID and client secret in Providers first.')
        if not self.token or time.monotonic()>=self.expires:
            response=self.transport('https://id.twitch.tv/oauth2/token',
                headers={'Content-Type':'application/x-www-form-urlencoded'},
                data=urlencode({'client_id':client,'client_secret':secret,'grant_type':'client_credentials'}).encode())
            self.token=response['access_token']; self.expires=time.monotonic()+max(0,int(response.get('expires_in',0))-60)
        wait=.26-(time.monotonic()-self.last)
        if wait>0: time.sleep(wait)
        self.last=time.monotonic()
        return self.transport('https://api.igdb.com/v4/games',headers={'Client-ID':client,'Authorization':'Bearer '+self.token,'Content-Type':'text/plain'},data=query.encode())
    def search(self,query):
        # JSON quoting also safely escapes the IGDB query string literal.
        clause=f'where id = {int(query)};' if query.strip().isdigit() else 'search '+json.dumps(query.strip())+';'
        result=self._query(clause+' fields name,first_release_date; limit 25;')
        return [{'id':g['id'],'name':g['name']} for g in result]
    def fetch(self,game_id):
        game_id=int(game_id)
        if game_id<=0: raise ValueError('Invalid IGDB ID.')
        result=self._query(f'where id = {game_id}; fields name,summary,storyline,first_release_date,genres.name,involved_companies.company.name,involved_companies.developer,involved_companies.publisher,cover.image_id,artworks.image_id; limit 1;')
        if not result: raise ValueError('IGDB game not found.')
        g=result[0]; companies=g.get('involved_companies',[])
        info={'title':g['name'],'description':'\n\n'.join(s for s in (g.get('summary'),g.get('storyline')) if s),
              'release_date':datetime.fromtimestamp(g['first_release_date'],timezone.utc).strftime('%Y-%m-%d') if g.get('first_release_date') else '',
              'developers':', '.join(c['company']['name'] for c in companies if c.get('developer')),
              'publishers':', '.join(c['company']['name'] for c in companies if c.get('publisher')),
              'genres':', '.join(x['name'] for x in g.get('genres',[]))}
        sources={}
        if g.get('cover'): sources['portrait']=('cover_big',g['cover']['image_id'])
        if g.get('artworks'): sources['hero']=('screenshot_big',g['artworks'][0]['image_id'])
        art={}; missing=[]
        for kind,(size,image_id) in sources.items():
            if not re.fullmatch(r'[a-zA-Z0-9_]+',image_id): continue
            try:
                data=metadata.request(f'https://images.igdb.com/igdb/image/upload/t_{size}/{image_id}.jpg',MAX_IMAGE)
                image_extension(data); art[kind]=data
            except Exception: missing.append(kind)
        return info,art,missing


class SteamGridDB:
    def __init__(self,credentials,transport=api_request): self.credentials=credentials; self.transport=transport
    def _get(self,path):
        key=self.credentials.load()['steamgriddb_key']
        if not key: raise ValueError('Add your SteamGridDB API key in Providers first.')
        response=self.transport('https://www.steamgriddb.com/api/v2/'+path,headers={'Authorization':'Bearer '+key})
        if not response.get('success'): raise ValueError('SteamGridDB could not complete this request.')
        return response['data']
    def search(self,query):
        return self._get('search/autocomplete/'+quote(query.strip(),safe=''))[:25]
    def artwork(self,game_id,kind):
        endpoints={'portrait':'grids','landscape':'grids','hero':'heroes','logo':'logos','icon':'icons'}
        params={'types':'static','mimes':'image/png,image/jpeg','nsfw':'false','humor':'false'}
        if kind in ('portrait','landscape'): params['dimensions']='600x900' if kind=='portrait' else '460x215,920x430'
        results=self._get(f'{endpoints[kind]}/game/{int(game_id)}?'+urlencode(params))
        return [{'id':x['id'],'url':x['url'],'thumb':x.get('thumb',x['url']),
                 'author':x.get('author',{}).get('name','Unknown artist'),
                 'width':x.get('width',0),'height':x.get('height',0)} for x in results[:12] if x.get('mime') in ('image/png','image/jpeg')]
