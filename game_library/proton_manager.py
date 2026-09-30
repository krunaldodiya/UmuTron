"""Official GE/UMU releases, staged checksum-verified runner installation."""
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import tarfile
import tempfile
import threading
import time
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .library import atomic_write
from .launcher import discover

REPOS={'GE-Proton':'GloriousEggroll/proton-ge-custom','UMU-Proton':'Open-Wine-Components/umu-proton'}
HOSTS={'api.github.com','github.com','objects.githubusercontent.com','release-assets.githubusercontent.com'}
MAX_DOWNLOAD=2*1024**3
MAX_EXPANDED=8*1024**3


def trusted(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):raise ValueError('Unexpected upstream download address.')
    return url


class Redirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        trusted(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)


def fetch(url):
    with build_opener(Redirects).open(Request(trusted(url),headers={'User-Agent':'GameLibraryLauncher/0.2','Accept':'application/vnd.github+json'}),timeout=25) as response:
        data=response.read(4*1024*1024+1)
    if len(data)>4*1024*1024:raise ValueError('Release response is too large.')
    return json.loads(data)


def release_items(payload,family,arch):
    results=[];repo=REPOS[family]
    for release in payload:
        if release.get('draft') or release.get('prerelease'):continue
        tag=release.get('tag_name','')
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,100}',tag):continue
        assets=release.get('assets',[])
        for asset in assets:
            name=asset.get('name','')
            if not name.endswith('.tar.gz'):continue
            architecture='aarch64' if 'aarch64' in name or 'arm64' in name else 'x86_64'
            if architecture!=arch:continue
            major=re.search(r'(?:GE-Proton|UMU-Proton-?)(\d+)',tag)
            if major and int(major[1])<9:continue
            url=asset.get('browser_download_url','')
            if not url.startswith('https://github.com/'+repo+'/releases/download/'):continue
            checks=next((a for a in assets if a.get('name')==name.removesuffix('.tar.gz')+'.sha512sum'),None)
            digest=asset.get('digest') or ''
            if not checks and not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):continue
            if checks and not checks.get('browser_download_url','').startswith('https://github.com/'+repo+'/releases/download/'):continue
            size=asset.get('size',0)
            if type(size) is not int or not 0<size<=MAX_DOWNLOAD:continue
            results.append({'family':family,'version':tag,'architecture':architecture,'name':name,'url':url,'size':size,'digest':digest,'checksum_url':checks['browser_download_url'] if checks else '', 'source':'https://github.com/'+repo})
    return results


def download(url,destination,limit,cancel,progress):
    with build_opener(Redirects).open(Request(trusted(url),headers={'User-Agent':'GameLibraryLauncher/0.2'}),timeout=25) as response,Path(destination).open('xb') as output:
        size=0
        while chunk:=response.read(1024*1024):
            if cancel.is_set():raise InterruptedError('Installation cancelled.')
            size+=len(chunk)
            if size>limit:raise ValueError('Download exceeds expected size.')
            output.write(chunk);progress(size)
        output.flush();os.fsync(output.fileno())
    return size


def extract(archive,destination,cancel):
    destination=Path(destination)
    with tarfile.open(archive,'r:gz') as tar:
        members=[];total=0;roots=set();seen=set()
        for item in tar:
            if cancel.is_set():raise InterruptedError('Installation cancelled.')
            path=PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or '\\' in item.name or not path.parts:raise ValueError('Unsafe archive path.')
            if not (item.isdir() or item.isfile() or item.issym() or item.islnk()):raise ValueError('Unsupported archive entry.')
            key=str(path)
            if key in seen and not item.isdir():raise ValueError('Duplicate archive entry.')
            seen.add(key);roots.add(path.parts[0]);total+=item.size
            if total>MAX_EXPANDED or len(members)>=150000:raise ValueError('Runner archive exceeds safe limits.')
            members.append(item)
        if len(roots)!=1:raise ValueError('Runner archive must have one top-level folder.')
        if shutil.disk_usage(destination).free<total+128*1024**2:raise ValueError('Not enough free space to extract this runner.')
        # Extract files before links; never write a file through an archive-created symlink.
        for item in members:
            if item.issym() or item.islnk():continue
            target=destination/item.name
            if item.isdir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(item) as source,target.open('xb') as out:
                    while chunk:=source.read(1024*1024):
                        if cancel.is_set():raise InterruptedError('Installation cancelled.')
                        out.write(chunk)
                target.chmod(item.mode&0o777)
        for item in members:
            if not (item.issym() or item.islnk()):continue
            if cancel.is_set():raise InterruptedError('Installation cancelled.')
            target=destination/item.name;target.parent.mkdir(parents=True,exist_ok=True)
            link=(target.parent/item.linkname) if item.issym() else (destination/item.linkname)
            if PurePosixPath(item.linkname).is_absolute() or not link.resolve().is_relative_to(destination.resolve()):raise ValueError('Archive link escapes the installation.')
            if item.issym():target.symlink_to(item.linkname)
            else:
                if not link.is_file() or link.is_symlink():raise ValueError('Invalid archive hard link.')
                os.link(link,target)
        root=destination/next(iter(roots))
        if not (root/'proton').is_file() or not (root/'proton').resolve().is_relative_to(root.resolve()):raise ValueError('Archive has no usable proton launcher.')
        # Verify all link chains after creation as well.
        for item in members:
            if item.issym() and not (destination/item.name).resolve().is_relative_to(root.resolve()):raise ValueError('Archive link chain escapes the runner.')
        return root


class ProtonManager:
    def __init__(self,root,transport=fetch,downloader=download,arch=None):
        self.root=Path(root);self.tools=self.root/'runners';self.tools.mkdir(parents=True,exist_ok=True)
        self.transport=transport;self.downloader=downloader;self.arch=arch or platform.machine()
        self.lock=threading.Lock();self.jobs={}

    def installed(self):
        paths=set(discover()['protons']);paths|={str(p) for p in self.tools.iterdir() if p.is_dir() and (p/'proton').is_file() and not p.name.startswith('.')}
        return sorted(paths)

    def releases(self,family,page=1,refresh=False):
        if family not in REPOS or type(page) is not int or not 1<=page<=100:raise ValueError('Invalid release page.')
        if self.arch not in ('x86_64','aarch64'):raise ValueError('Runner downloads currently support x86_64 and aarch64 hosts only.')
        cache=self.root/f'releases-{family}-{page}.json'
        if cache.is_file() and not refresh and time.time()-cache.stat().st_mtime<3600:
            data=json.loads(cache.read_text())
        else:
            data=self.transport(f'https://api.github.com/repos/{REPOS[family]}/releases?per_page=20&page={page}')
            if not isinstance(data,list):raise ValueError('Invalid upstream release response.')
            atomic_write(cache,json.dumps(data).encode())
        return release_items(data,family,self.arch)

    def status(self,release):
        with self.lock:
            if release['name'] in self.jobs:return dict(self.jobs[release['name']])
        match=next((p for p in self.installed() if Path(p).name==release['name'].removesuffix('.tar.gz') or Path(p).name==release['version']),None)
        return {'state':'Installed' if match else 'Available','path':match or '','progress':0,'error':''}

    def cancel(self,release):
        with self.lock:
            job=self.jobs.get(release['name'])
            if job and job['state'] in ('Downloading','Verifying','Installing'):job['cancel'].set()

    def install(self,release,active_runner=None):
        name=release['name']
        repo=REPOS.get(release.get('family'))
        if not repo or not release.get('url','').startswith('https://github.com/'+repo+'/releases/download/'):raise ValueError('Runner source is not an official supported release.')
        checksum=release.get('checksum_url','')
        if checksum and not checksum.startswith('https://github.com/'+repo+'/releases/download/'):raise ValueError('Unexpected checksum source.')
        if release.get('architecture')!=self.arch:raise ValueError('Runner architecture does not match this host.')
        if not re.fullmatch(r'[A-Za-z0-9._-]+\.tar\.gz',name):raise ValueError('Invalid runner release name.')
        with self.lock:
            job=self.jobs.get(name)
            if job and job['state'] in ('Downloading','Verifying','Installing'):raise RuntimeError('This installation is already in progress.')
            if any(j['state'] in ('Downloading','Verifying','Installing') for j in self.jobs.values()):raise RuntimeError('Another runner installation is active. Wait or cancel it first.')
            if (self.tools/name.removesuffix('.tar.gz')).exists():raise ValueError('That runner is already installed; it will not be overwritten.')
            job={'state':'Downloading','progress':0,'error':'','path':'','cancel':threading.Event()};self.jobs[name]=job
        threading.Thread(target=self._install,args=(release,job,active_runner),daemon=True).start()

    def _install(self,release,job,active_runner):
        fd=os.open(self.root/'runner-install.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            for stale in self.tools.glob('.install-*'):
                if stale.is_dir() and not stale.is_symlink():shutil.rmtree(stale)
            if shutil.disk_usage(self.tools).free<release['size']*5+128*1024**2:raise ValueError('Not enough free space for download and extraction.')
            with tempfile.TemporaryDirectory(prefix='.install-',dir=self.tools) as temp:
                folder=Path(temp);archive=folder/release['name']
                self.downloader(release['url'],archive,release['size'],job['cancel'],lambda n:self._update(job,progress=min(1,n/release['size'])))
                if archive.stat().st_size!=release['size']:raise ValueError('Incomplete runner download.')
                self._update(job,state='Verifying')
                digest=release.get('digest','')
                if digest.startswith('sha256:'):
                    with archive.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
                    if actual!=digest.split(':',1)[1]:raise ValueError('Runner checksum verification failed.')
                if release.get('checksum_url'):
                    checksum=folder/'checksum.txt';self.downloader(release['checksum_url'],checksum,16384,job['cancel'],lambda _:None)
                    lines=checksum.read_text().splitlines();expected=None
                    for line in lines:
                        parts=line.split()
                        if len(parts)>=2 and parts[-1].lstrip('*')==release['name'] and re.fullmatch(r'[a-fA-F0-9]{128}',parts[0]):expected=parts[0].lower()
                    if expected is None:raise ValueError('Published checksum does not identify this runner archive.')
                    with archive.open('rb') as f:actual=hashlib.file_digest(f,'sha512').hexdigest()
                    if actual!=expected:raise ValueError('Published runner checksum verification failed.')
                elif not digest.startswith('sha256:'):raise ValueError('No published checksum available.')
                if job['cancel'].is_set():raise InterruptedError('Installation cancelled.')
                self._update(job,state='Installing');stage=folder/'unpacked';stage.mkdir()
                runner=extract(archive,stage,job['cancel']);target=self.tools/release['name'].removesuffix('.tar.gz')
                if target.exists() or (active_runner and Path(active_runner).resolve()==target.resolve()):raise ValueError('Runner already exists or is in use; it was preserved.')
                if job['cancel'].is_set():raise InterruptedError('Installation cancelled.')
                runner.rename(target);self._update(job,state='Installed',progress=1,path=str(target))
        except Exception as error:self._update(job,state='Cancelled' if isinstance(error,InterruptedError) else 'Failed',error=str(error)[:1000])
        finally:os.close(fd)

    def _update(self,job,**changes):
        with self.lock:job.update(changes)

    def busy(self):
        with self.lock:return any(j['state'] in ('Downloading','Verifying','Installing') for j in self.jobs.values())
