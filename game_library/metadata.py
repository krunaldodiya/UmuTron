"""Bounded provider image downloads and plain-text conversion."""
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

ALLOWED=('images.igdb.com','cdn2.steamgriddb.com','cdn.steamgriddb.com')


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
    req=Request(allowed(url),headers={'User-Agent':'GameLibraryLauncher/0.2'})
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
