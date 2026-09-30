"""Public Steam Store lookup; bounded HTTPS requests, no account credentials."""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .library import MAX_IMAGE, image_extension

ALLOWED=('store.steampowered.com','cdn.akamai.steamstatic.com','cdn.cloudflare.steamstatic.com',
         'shared.akamai.steamstatic.com','shared.fastly.steamstatic.com',
         'shared.cloudflare.steamstatic.com','steamcdn-a.akamaihd.net',
         'images.igdb.com','cdn2.steamgriddb.com','cdn.steamgriddb.com')


def allowed(url):
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Unexpected metadata download address.')
    return url


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def request(url,limit=4*1024*1024):
    req=Request(allowed(url),headers={'User-Agent':'GameLibraryLauncher/0.3'})
    with build_opener(Redirects).open(req,timeout=15) as response:
        allowed(response.url)
        data=response.read(limit+1)
    if len(data)>limit: raise ValueError('Response exceeds download limit.')
    return data


class PlainText(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self,data): self.parts.append(data)
    def handle_starttag(self,tag,attrs):
        if tag in ('br','p','li','h1','h2'): self.parts.append('\n')


def plain(value):
    parser=PlainText(); parser.feed(value); return ''.join(parser.parts).strip()


def details(app_id):
    app_id=int(app_id)
    if app_id<=0: raise ValueError('Enter a positive Steam store ID.')
    payload=json.loads(request('https://store.steampowered.com/api/appdetails?'+urlencode({'appids':app_id,'l':'english','cc':'us'})))
    result=payload.get(str(app_id),{})
    if not result.get('success'): raise ValueError('No public Steam store details found for this ID.')
    data=result['data']
    return {'metadata_app_id':app_id,'title':data['name'],
            'description':plain(data.get('detailed_description') or data.get('short_description','')),
            'release_date':data.get('release_date',{}).get('date',''),
            'developers':', '.join(data.get('developers',[])),
            'publishers':', '.join(data.get('publishers',[])),
            'genres':', '.join(g['description'] for g in data.get('genres',[])),
            'header_url':data.get('header_image','')}


def search(query):
    query=query.strip()
    if not query: raise ValueError('Enter a game name or Steam store ID.')
    if query.isdecimal():
        item=details(int(query))
        return [{'id':item['metadata_app_id'],'name':item['title']}]
    payload=json.loads(request('https://store.steampowered.com/api/storesearch/?'+urlencode({'term':query,'l':'english','cc':'us'})))
    return [{'id':int(i['id']),'name':i['name']} for i in payload.get('items',[])[:30] if i.get('type')=='app']


def fetch_game(app_id):
    info=details(app_id)
    base=f'https://cdn.akamai.steamstatic.com/steam/apps/{int(app_id)}/'
    sources={'portrait':base+'library_600x900_2x.jpg',
             'landscape':info.pop('header_url') or base+'header.jpg',
             'hero':base+'library_hero.jpg','logo':base+'logo.png'}
    artwork={}; missing=[]
    def download(item):
        kind,url=item
        try:
            content=request(url,MAX_IMAGE); image_extension(content)
            return kind,content
        except Exception: return kind,None
    with ThreadPoolExecutor(max_workers=4) as pool:
        for kind,content in pool.map(download,sources.items()):
            if content: artwork[kind]=content
            else: missing.append(kind)
    # Store APIs do not reliably expose shortcut icons; the UI allows local selection.
    return info,artwork,missing
