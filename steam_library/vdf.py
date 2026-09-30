"""Lossless typed binary KeyValues reader/writer for Steam shortcuts.

Unknown types, duplicate keys and malformed input are refused, never discarded.
"""
import struct

MAX_BYTES=32*1024*1024


def loads(raw):
    if len(raw)>MAX_BYTES: raise ValueError('Steam shortcuts file is too large.')
    pos=0
    def take(n):
        nonlocal pos
        if pos+n>len(raw): raise ValueError('Truncated Steam shortcuts file.')
        value=raw[pos:pos+n]; pos+=n; return value
    def string():
        nonlocal pos
        end=raw.find(b'\0',pos)
        if end<0: raise ValueError('Unterminated Steam string.')
        value=raw[pos:end].decode('utf-8',errors='surrogateescape'); pos=end+1
        return value
    def obj(depth):
        if depth>32: raise ValueError('Steam data is nested too deeply.')
        out={}
        while True:
            kind=take(1)[0]
            if kind==8: return out
            key=string()
            if key in out: raise ValueError('Duplicate Steam key.')
            if kind==0: value=obj(depth+1)
            elif kind==1: value=string()
            elif kind in (2,3,4,6): value=take(4)
            elif kind in (7,10): value=take(8)
            elif kind==5:
                size=take(2); value=size+take(struct.unpack('<H',size)[0]*2)
            else: raise ValueError('Unsupported Steam field type: '+str(kind))
            out[key]=(kind,value)
    result=obj(0)
    if pos!=len(raw): raise ValueError('Trailing data in Steam shortcuts file.')
    return result


def dumps(tree):
    def string(s):
        if '\0' in s: raise ValueError('Steam strings cannot contain NUL.')
        return s.encode('utf-8',errors='surrogateescape')+b'\0'
    def obj(data):
        out=bytearray()
        for key,(kind,value) in data.items():
            out.append(kind); out.extend(string(key))
            out.extend(obj(value) if kind==0 else string(value) if kind==1 else value)
        out.append(8); return bytes(out)
    return obj(tree)


def text(value): return (1,value)
def integer(value): return (2,struct.pack('<I',value & 0xffffffff))
def value(entry, key, default=''):
    field=next((v for k,v in entry.items() if k.casefold()==key.casefold()),None)
    if field is None: return default
    if field[0]==1: return field[1]
    if field[0]==2: return struct.unpack('<I',field[1])[0]
    return default

def put(entry,key,field):
    found=next((k for k in entry if k.casefold()==key.casefold()),key)
    entry[found]=field
