"""IGDB catalog contracts, bounded local snapshots and explicit library membership.

IGDBCatalog accepts a server-side query function. The desktop uses RemoteCatalog;
no Twitch secret, authentication grant or undocumented Steam fallback lives here.
"""
from copy import deepcopy
from concurrent.futures import Future
from datetime import datetime, timezone
from hashlib import sha256
import json
import ipaddress
import os
from pathlib import Path
import re
import stat
import threading
import time
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .library import atomic_write, image_extension, MAX_IMAGE
from .providers import api_request
from . import metadata

PAGE_SIZE = 24
MAX_PAGE = 1000
FIELDS = ('name,summary,storyline,first_release_date,genres.name,cover.image_id,'
          'artworks.image_id,involved_companies.company.name,involved_companies.developer,'
          'involved_companies.publisher,version_parent,version_title')


def positive(value):
    if type(value) is not int or value <= 0: raise ValueError('Invalid catalog identity.')
    return value


def text(value, limit=100000):
    if not isinstance(value, str) or len(value) > limit or '\0' in value:
        raise ValueError('Invalid catalog text.')
    return value


def image_url(image_id, size):
    if not isinstance(image_id,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,120}',image_id): return None
    return f'https://images.igdb.com/igdb/image/upload/t_{size}/{image_id}.jpg'


def reference(value,name_limit=1000):
    if not isinstance(value,dict):raise ValueError('Invalid catalog reference.')
    identity=positive(value.get('id'));name=text(value.get('name'),name_limit).strip()
    if identity>9007199254740991 or not name:raise ValueError('Invalid catalog reference.')
    return {'id':identity,'name':name}


def references(values,*,selected=None,name_limit=1000):
    if not isinstance(values,list) or len(values)>100:raise ValueError('Invalid catalog reference list.')
    result=[reference(value,name_limit) for value in values]
    identities=[value['id'] for value in result]
    if len(set(identities))!=len(identities) or selected in identities:raise ValueError('Invalid catalog reference identities.')
    return result


def relationships(value,selected):
    if not isinstance(value,dict):raise ValueError('Invalid catalog relationships.')
    result={key:references(value.get(key,[]),selected=selected) for key in ('bundles','expanded_games')}
    for key in ('parent_game','version_parent'):
        target=value.get(key)
        result[key]=references([target],selected=selected)[0] if target is not None else None
    for key in ('bundle_contents','expanded_from'):
        if key not in value:continue
        group=value[key]
        if not isinstance(group,dict) or type(group.get('complete')) is not bool:raise ValueError('Invalid catalog relationship completeness.')
        result[key]={'items':references(group.get('items'),selected=selected),'complete':group['complete']}
    return result


def validate_item(item):
    if not isinstance(item,dict): raise ValueError('Invalid catalog item.')
    result={'id':positive(item.get('id')),'name':text(item.get('name'),1000)}
    if not result['name'].strip(): raise ValueError('Catalog item has no title.')
    for key in ('description','release_date','developers','publishers','version_title'):
        result[key]=text(item.get(key,''))
    genres=item.get('genres',[])
    if not isinstance(genres,list) or len(genres)>100: raise ValueError('Invalid catalog genres.')
    result['genres']=[{'id':positive(g.get('id')),'name':text(g.get('name'),200)} for g in genres]
    # Additive backend fields: absence in old responses/snapshots means unknown.
    kind=item.get('game_type')
    result['game_type']=(text(kind,64).strip() or None) if kind is not None else None
    result['platforms']=references(item.get('platforms',[]),name_limit=200)
    if 'relationships' in item:result['relationships']=relationships(item['relationships'],result['id'])
    result['images']={}
    images=item.get('images',{})
    if not isinstance(images,dict) or set(images)-{'portrait','hero'}: raise ValueError('Invalid catalog artwork.')
    for kind,url in images.items():
        if not isinstance(url,str) or not re.fullmatch(r'https://images\.igdb\.com/igdb/image/upload/t_(cover_big|screenshot_big)/[A-Za-z0-9_]{1,120}\.jpg',url):
            raise ValueError('Unexpected catalog artwork address.')
        result['images'][kind]=url
    result['steam_app_id']=positive(item['steam_app_id']) if item.get('steam_app_id') is not None else None
    return result


def normalize(game):
    companies=game.get('involved_companies',[])
    images={}
    cover=image_url(game.get('cover',{}).get('image_id'),'cover_big')
    hero=image_url(next(iter(game.get('artworks',[])),{}).get('image_id'),'screenshot_big')
    if cover:images['portrait']=cover
    if hero:images['hero']=hero
    date=game.get('first_release_date')
    return validate_item({'id':game['id'],'name':game['name'],
        'description':'\n\n'.join(text(s) for s in (game.get('summary'),game.get('storyline')) if s),
        'release_date':datetime.fromtimestamp(date,timezone.utc).strftime('%Y-%m-%d') if date else '',
        'developers':', '.join(text(c['company']['name']) for c in companies if c.get('developer')),
        'publishers':', '.join(text(c['company']['name']) for c in companies if c.get('publisher')),
        'genres':game.get('genres',[]),'images':images,'version_title':game.get('version_title','')})


def steam_id(rows, game_id):
    """Only current source relations for this exact IGDB record; never guess editions."""
    ids=set()
    for row in rows:
        source=row.get('external_game_source',{})
        if row.get('game')!=game_id or not isinstance(source,dict) or source.get('name','').casefold()!='steam':continue
        uid=row.get('uid','')
        if not isinstance(uid,str) or not re.fullmatch(r'[1-9][0-9]{0,9}',uid): return None
        value=int(uid); ids.add(value)
        url=row.get('url')
        if url:
            parsed=urlparse(url)
            if parsed.scheme!='https' or parsed.hostname!='store.steampowered.com' or parsed.username or parsed.password or parsed.port not in (None,443):return None
            if not re.match(r'/app/'+str(value)+r'(?:/|$)',parsed.path):return None
    return next(iter(ids)) if len(ids)==1 else None


class IGDBCatalog:
    def __init__(self,query):self.query=query

    def genres(self):
        rows=self.query('genres','fields name; sort name asc; limit 100;')
        return [{'id':positive(g['id']),'name':text(g['name'],200)} for g in rows[:100]]

    def browse(self,query='',genre=None,page=1):
        query=text(query,200).strip();positive(page)
        if page>MAX_PAGE:raise ValueError('Narrow your search to see more games.')
        if genre is not None:positive(genre)
        clause='search '+json.dumps(query)+';' if query else 'sort name asc;'
        if genre is not None:clause+=f' where genres = {genre};'
        rows=self.query('games',f'{clause} fields {FIELDS}; limit {PAGE_SIZE+1}; offset {(page-1)*PAGE_SIZE};')
        if not isinstance(rows,list) or len(rows)>PAGE_SIZE+1:raise ValueError('Unexpected catalog page size.')
        return {'items':[normalize(g) for g in rows[:PAGE_SIZE]],'has_next':len(rows)>PAGE_SIZE,'page':page}

    def detail(self,game_id):
        positive(game_id)
        rows=self.query('games',f'fields {FIELDS}; where id = {game_id}; limit 1;')
        if len(rows)!=1 or rows[0].get('id')!=game_id:raise ValueError('This title is no longer available in the catalog.')
        item=normalize(rows[0])
        external=self.query('external_games',f'fields game,external_game_source.name,uid,url; where game = {game_id}; limit 100;')
        # A full result could be truncated; do not assert a unique mapping then.
        if len(external)<100:item['steam_app_id']=steam_id(external,game_id)
        return item


class UnconfiguredCatalog:
    def __init__(self,message='Store is not connected yet. Your library is available offline.'):self.message=message
    def unavailable(self,*_):raise ValueError(self.message)
    genres=browse=detail=unavailable


def catalog_endpoint(base_url,allow_loopback_http=False):
    """HTTPS by default; opt-in HTTP is pinned to a numeric loopback address."""
    message='APP_BASE_URL must be an HTTPS origin without paths or credentials. Local HTTP needs UMUTRON_ALLOW_LOOPBACK_HTTP=1 and a loopback host.'
    if not isinstance(base_url,str) or any(c.isspace() or ord(c)<32 or ord(c)==127 for c in base_url):raise ValueError(message)
    try:
        parsed=urlparse(base_url);host=parsed.hostname;port=parsed.port
        if not host or parsed.username is not None or parsed.password is not None or parsed.path not in ('','/') or parsed.params or parsed.query or parsed.fragment or port==0:
            raise ValueError(message)
        if parsed.scheme=='https':return parsed.geturl().rstrip('/'),False
        if parsed.scheme!='http' or allow_loopback_http is not True:raise ValueError(message)
        if host.lower()=='localhost':address=ipaddress.ip_address('127.0.0.1')
        else:
            if '%' in host:raise ValueError(message)
            address=ipaddress.ip_address(host)
        if not address.is_loopback or (address.version==6 and address.ipv4_mapped is not None):raise ValueError(message)
        # Do not let hosts-file/DNS/proxy configuration turn localhost into a
        # remote destination. Only this literal loopback address is requested.
        authority=f'[{address}]' if address.version==6 else str(address)
        if port is not None:authority+=':'+str(port)
        return parsed._replace(netloc=authority).geturl().rstrip('/'),True
    except (ValueError,TypeError):raise ValueError(message) from None


class CatalogNoRedirects(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Catalog redirects are not followed.')


def loopback_request(url):
    parsed=urlparse(url)
    origin,local=catalog_endpoint(parsed._replace(path='',params='',query='',fragment='').geturl(),allow_loopback_http=True)
    if parsed.fragment or parsed.params or not (parsed.path in ('/v1/genres','/v1/games') or re.fullmatch(r'/v1/games/[1-9][0-9]*',parsed.path)):
        raise ValueError('Unexpected catalog request path.')
    endpoint=origin+parsed.path
    if parsed.query:endpoint+='?'+parsed.query
    if not local:raise ValueError('Development transport requires loopback HTTP.')
    request=Request(endpoint,headers={'User-Agent':'UmuTron/catalog-development','Accept':'application/json'})
    with build_opener(ProxyHandler({}),CatalogNoRedirects).open(request,timeout=20) as response:
        body=response.read(4*1024*1024+1)
    if len(body)>4*1024*1024:raise ValueError('Catalog response is too large.')
    return json.loads(body)


class RemoteCatalog:
    """Normalized backend contract; no credentials, library data or local paths."""
    def __init__(self,base_url,transport=None,*,allow_loopback_http=False):
        self.base,self.development=catalog_endpoint(base_url,allow_loopback_http)
        self.transport=transport if transport is not None else loopback_request if self.development else api_request
    def genres(self):return self.transport(self.base+'/v1/genres')
    def browse(self,query='',genre=None,page=1):
        return self.transport(self.base+'/v1/games?'+urlencode({'q':query,'genre':genre or '', 'page':page}))
    def detail(self,game_id):return self.transport(self.base+'/v1/games/'+str(positive(game_id)))


def configured_catalog(environ=None, *, config_path=None):
    """Resolve a nonsecret endpoint; injected environments use only supplied files.

    Environment APP_BASE_URL overrides catalog.json, then the legacy environment
    alias is used only if no primary exists. Invalid primaries never fall back.
    """
    values=os.environ if environ is None else environ
    endpoint=values.get('APP_BASE_URL')
    if endpoint is None:
        if config_path is None and environ is None:
            config_dir=Path(values.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'umutron'
            legacy_dir=Path(values.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'game-library-launcher'
            if (config_dir/'catalog.json').exists():config_path=config_dir/'catalog.json'
            elif (legacy_dir/'catalog.json').exists():config_path=legacy_dir/'catalog.json'
            else:config_path=config_dir/'catalog.json'
        if config_path is not None:
            try:
                fd=os.open(config_path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
                with os.fdopen(fd,'rb') as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError()
                    raw=stream.read(16385)
                if len(raw)>16384:raise ValueError()
                settings=json.loads(raw)
                if not isinstance(settings,dict) or set(settings)!={'APP_BASE_URL'} or not isinstance(settings['APP_BASE_URL'],str):raise ValueError()
                endpoint=settings['APP_BASE_URL']
            except FileNotFoundError:pass
            except (OSError,ValueError):return UnconfiguredCatalog('Catalog configuration could not be read. Check the nonsecret catalog.json APP_BASE_URL setting.')
        if endpoint is None:endpoint=values.get('UMUTRON_CATALOG_URL','')
    if not isinstance(endpoint,str):return UnconfiguredCatalog('APP_BASE_URL must be an HTTPS origin.')
    endpoint=endpoint.strip()
    if not endpoint:return UnconfiguredCatalog()
    try:return RemoteCatalog(endpoint,allow_loopback_http=values.get('UMUTRON_ALLOW_LOOPBACK_HTTP')=='1')
    except ValueError as error:return UnconfiguredCatalog(str(error))


class CatalogService:
    """Validated origin-scoped snapshots; transport never holds a file lock."""
    def __init__(self,provider,root,image_transport=metadata.request):
        self.provider=provider;self.root=Path(root);self.image_transport=image_transport
        self.scope=('remote:'+provider.base if isinstance(provider,RemoteCatalog)
                    else 'adapter:'+type(provider).__module__+'.'+type(provider).__qualname__)
        self.lock=threading.RLock();self.image_lock=threading.RLock()
        self.flight_lock=threading.RLock();self.flights={}

    def _path(self,key):
        return self.root/(sha256(json.dumps(['snapshot-v2',self.scope,key]).encode()).hexdigest()+'.json')

    @staticmethod
    def _cache_bytes(path,limit,lock):
        with lock:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise ValueError('Invalid cache file.')
                raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('Oversized cache file.')
        return raw

    def _snapshot(self,key,validate):
        try:
            raw=self._cache_bytes(self._path(key),4*1024*1024,self.lock)
            saved=json.loads(raw)
            if not isinstance(saved,dict) or set(saved)!={'scope','key','at','value'}:raise ValueError('Invalid catalog snapshot.')
            stamp=saved['at']
            if (saved['scope']!=self.scope or saved['key']!=key or type(stamp) is not int
                    or not 0<stamp<=int(time.time())+300):raise ValueError('Invalid catalog snapshot identity.')
            return validate(saved['value']),stamp
        except Exception:return None

    @staticmethod
    def _prune(folder,pattern,limit):
        files=[]
        for path in folder.glob(pattern):
            try:files.append((path.stat().st_mtime_ns,path))
            except FileNotFoundError:continue
        for _,path in sorted(files,reverse=True)[limit:]:path.unlink(missing_ok=True)

    def _singleflight(self,key,work):
        with self.flight_lock:
            future=self.flights.get(key);leader=future is None
            if leader:
                if len(self.flights)>=8:raise ValueError('Catalog is busy. Try again shortly.')
                future=Future();self.flights[key]=future
        if leader:
            try:future.set_result(work())
            except BaseException as error:future.set_exception(error)
            finally:
                with self.flight_lock:self.flights.pop(key,None)
        # Callers can enrich their own result without changing another caller's
        # page or the shared completed result. UI cancellation owns no flight.
        return deepcopy(future.result())

    def _load(self,key,work,validate):
        def refresh():
            try:value=validate(work());stamp=int(time.time())
            except Exception:
                saved=self._snapshot(key,validate)
                if saved is None:raise
                value,stamp=saved;return value,True,stamp
            try:
                with self.lock:
                    self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
                    body=json.dumps({'scope':self.scope,'key':key,'at':stamp,'value':value}).encode()
                    if len(body)<=4*1024*1024:atomic_write(self._path(key),body)
                    self._prune(self.root,'*.json',100)
            except OSError:pass # A disposable-cache write cannot hide valid fresh cards.
            return value,False,stamp
        return self._singleflight(('metadata',key),refresh)

    @staticmethod
    def _genres(rows):
        if not isinstance(rows,list) or len(rows)>100:raise ValueError('Invalid genre list.')
        return [{'id':positive(g['id']),'name':text(g['name'],200)} for g in rows]

    def cached_genres(self):
        saved=self._snapshot('genres',self._genres)
        return saved[0] if saved is not None else None

    def genres(self):return self._load('genres',self.provider.genres,self._genres)[0]

    @staticmethod
    def _page(query,genre,page):
        query=text(query,200).strip();positive(page)
        if page>MAX_PAGE:raise ValueError('Narrow your search to see more games.')
        if genre is not None:positive(genre)
        def validate(result):
            if not isinstance(result,dict) or result.get('page')!=page or type(result.get('has_next')) is not bool or not isinstance(result.get('items'),list) or len(result['items'])>PAGE_SIZE:
                raise ValueError('Invalid catalog page.')
            items=[validate_item(g) for g in result['items']]
            if len({i['id'] for i in items})!=len(items):raise ValueError('Repeated catalog identity.')
            value={'items':items,'page':page,'has_next':result['has_next']}
            if 'total_items' in result or 'total_pages' in result:
                count,pages=result.get('total_items'),result.get('total_pages')
                if (type(count) is not int or not 0<=count<=9007199254740991 or type(pages) is not int
                        or pages!=max(1,(count+PAGE_SIZE-1)//PAGE_SIZE)
                        or len(items)!=min(PAGE_SIZE,max(0,count-(page-1)*PAGE_SIZE))
                        or result['has_next']!=(page<pages and page<MAX_PAGE)):
                    raise ValueError('Invalid catalog totals.')
                value.update(total_items=count,total_pages=pages)
            return value
        return json.dumps(['page',query,genre,page]),query,validate

    def cached_browse(self,query='',genre=None,page=1):
        key,_,validate=self._page(query,genre,page);saved=self._snapshot(key,validate)
        if saved is None:return None
        value,stamp=saved
        return {**value,'cached':True,'refreshing':True,'fetched_at':stamp}

    def browse(self,query='',genre=None,page=1):
        key,query,validate=self._page(query,genre,page)
        value,cached,stamp=self._load(key,lambda:self.provider.browse(query,genre,page),validate)
        return {**value,'cached':cached,'fetched_at':stamp}

    def detail(self,game_id):
        positive(game_id)
        def validate(item):
            value=validate_item(item)
            if value['id']!=game_id:raise ValueError('Catalog identity changed.')
            return value
        value,cached,stamp=self._load(f'detail:{game_id}',lambda:self.provider.detail(game_id),validate)
        return {**value,'cached':cached,'fetched_at':stamp}

    def _cached_image(self,path):
        try:
            data=self._cache_bytes(path,MAX_IMAGE,self.image_lock)
            image_extension(data);return path
        except (OSError,ValueError):return None

    def image(self,url):
        validate_item({'id':1,'name':'Artwork','images':{'portrait':url}})
        path=self.root/'images'/(sha256(url.encode()).hexdigest()+'.jpg')
        cached=self._cached_image(path)
        if cached is not None:return cached
        def fetch():
            cached=self._cached_image(path)
            if cached is not None:return cached
            data=self.image_transport(url,MAX_IMAGE)
            if len(data)>MAX_IMAGE:raise ValueError('Catalog artwork is too large.')
            image_extension(data)
            with self.image_lock:
                path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);atomic_write(path,data)
                self._prune(path.parent,'*.jpg',160)
            return path
        return self._singleflight(('image',url),fetch)


def saved_steam_id(game):
    value=game.get('metadata_app_id');source=game.get('metadata_source',{})
    if source.get('provider')=='steam':
        source_id=source.get('id')
        if value is not None and value!=source_id:return None
        value=source_id
    return value if type(value) is int and value>0 else None


def members(library,item):
    """Membership tracks this exact catalog entity, never a shared store link."""
    item_id=positive(item['id'])
    return [g for g in library.games() if g.get('metadata_source')=={'provider':'igdb','id':item_id}]


def related_members(library,item):
    """A Steam association is a navigation hint, not ownership or identity."""
    item_id=positive(item['id']);steam=item.get('steam_app_id')
    if steam is None:return []
    positive(steam)
    return [g for g in library.games() if saved_steam_id(g)==steam
            and g.get('metadata_source')!={'provider':'igdb','id':item_id}]


def entity_label(item,compact=False):
    names={'main game':'Game','dlc addon':'DLC','expansion':'Expansion','bundle':'Bundle',
           'standalone expansion':'Standalone expansion','mod':'Mod','episode':'Episode',
           'season':'Season','remake':'Remake','remaster':'Remaster','expanded game':'Expanded game',
           'port':'Port','fork':'Fork','pack':'Pack','update':'Update'}
    kind=' '.join((item.get('game_type') or '').casefold().replace('_',' ').split())
    label=names.get(kind,'Catalog entry')
    platforms=list(dict.fromkeys(p['name'] for p in item.get('platforms',[])))
    if compact:
        platforms=['PC' if name=='PC (Microsoft Windows)' else name for name in platforms]
        if len(platforms)>1:platforms=[platforms[0]+f' +{len(platforms)-1}']
    return ' · '.join([label,*platforms])


def needs_membership_lookup(library,item):
    """A title only hints at a related Steam entry; it never proves membership."""
    if item.get('steam_app_id') is not None or members(library,item):return False
    name=' '.join(item['name'].casefold().split())
    return any(saved_steam_id(g) is not None and ' '.join(g['title'].casefold().split())==name for g in library.games())


def item_game(item,preview=False):
    from .library import Library, TEXT_FIELDS
    item=validate_item(item)
    game=({'id':'igdb:'+str(item['id']),'metadata_app_id':None,'metadata_source':{},'artwork':{},'sync':None,'launch':{},'installation':{},**{k:'' for k in TEXT_FIELDS}} if preview else Library.new_game())
    game.update(title=item['name'],description=item['description'],release_date=item['release_date'],
                developers=item['developers'],publishers=item['publishers'],genres=', '.join(g['name'] for g in item['genres']),
                metadata_source={'provider':'igdb','id':item['id']},metadata_app_id=item['steam_app_id'])
    return game


_add_lock=threading.RLock()


def add_item(library,item,artwork):
    # Async UI completions and repeated callers share the current library. Keep
    # membership check plus save one operation; no automatic merge or overwrite.
    with _add_lock:return _add_item(library,item,artwork)


def _add_item(library,item,artwork):
    item=validate_item(item);existing=members(library,item)
    if len(existing)>1:raise ValueError('Multiple saved copies exist. Open the desired copy in Library.')
    if existing:return existing[0],False
    game=item_game(item)
    for kind,data in artwork.items():
        if kind in ('portrait','hero'):game['artwork'][kind]=library.add_image(data)
    library.save(game)
    return deepcopy(game),True
