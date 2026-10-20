import json, os, re, subprocess, threading, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEVICE=os.getenv('CD_DEVICE','/dev/sr0')
PORT=int(os.getenv('PORT','8095'))
state_lock=threading.Lock()
active=set()


def run(args,timeout=15):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


def tracks():
    try:
        p=run(['cdparanoia','-d',DEVICE,'-Q'],20)
        raw=p.stdout+'\n'+p.stderr
        # cdparanoia prints table rows: 1.  12345 [02:44.45] ...
        out=[]
        for line in raw.splitlines():
            m=re.match(r'^\s*(\d+)\.\s+\d+\s+\[(\d+):(\d+)\.(\d+)\]',line)
            if m:
                n=int(m.group(1)); duration=int(m.group(2))*60+int(m.group(3))+int(m.group(4))/75
                out.append({'number':n,'duration':round(duration,2),'title':f'Piste {n}'})
        return {'tracks':out,'error': None if out else 'Aucun CD audio lisible détecté', 'diagnostic':raw[-1400:] if not out else None}
    except Exception as e:
        return {'tracks':[], 'error':str(e)}


def metadata():
    base=tracks()
    if not base['tracks']:
        return base
    try:
        p=run(['cd-discid',DEVICE],15)
        if p.returncode: return base
        discid=p.stdout.strip().split()[0]
        if not discid:return base
        url='https://musicbrainz.org/ws/2/discid/'+urllib.parse.quote(discid)+'?inc=recordings+artists&fmt=json'
        req=urllib.request.Request(url,headers={'User-Agent':'LecteurCDDocker/1.0 (private home audio player)','Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=7) as resp: data=json.load(resp)
        releases=data.get('releases') or []
        if not releases: return base
        release=releases[0]
        base['album']=release.get('title','')
        base['artist']=''.join(x.get('name','') for x in release.get('artist-credit',[]) if isinstance(x,dict))
        for med in release.get('media',[]):
            for t in med.get('tracks',[]):
                pos=t.get('position') or t.get('number')
                try: idx=int(pos)-1
                except (ValueError,TypeError): continue
                if 0<=idx<len(base['tracks']): base['tracks'][idx]['title']=t.get('title') or base['tracks'][idx]['title']
            if med.get('tracks'):break
    except Exception:
        pass
    return base


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def sendbytes(self,body,status=200,typ='application/json'):
        if isinstance(body,str):body=body.encode()
        self.send_response(status)
        self.send_header('Content-Type',typ)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)
    def api(self,obj,status=200):self.sendbytes(json.dumps(obj,ensure_ascii=False),status)
    def do_GET(self):
        parsed=urllib.parse.urlparse(self.path)
        if parsed.path=='/':
            self.sendbytes(Path('/app/index.html').read_bytes(),typ='text/html; charset=utf-8');return
        if parsed.path=='/api/tracks':self.api(tracks());return
        if parsed.path=='/api/metadata':self.api(metadata());return
        if parsed.path=='/stream':
            try:n=int(urllib.parse.parse_qs(parsed.query).get('track',['0'])[0])
            except ValueError:n=0
            current=tracks()
            if not any(x['number']==n for x in current['tracks']):self.api({'error':'Piste inexistante'},404);return
            self.stream(n);return
        self.api({'error':'Route inconnue'},404)
    def do_POST(self):
        route=urllib.parse.urlparse(self.path).path
        if route=='/api/eject':
            stop_all()
            try:
                p=run(['eject','-r',DEVICE],15)
                self.api({'ok':p.returncode==0,'message':(p.stderr or p.stdout).strip() or ('Tiroir éjecté' if p.returncode==0 else 'Éjection impossible')},200 if p.returncode==0 else 500)
            except Exception as e:self.api({'ok':False,'message':str(e)},500)
            return
        if route=='/api/close':
            try:
                p=run(['eject','-t',DEVICE],15)
                self.api({'ok':p.returncode==0,'message':(p.stderr or p.stdout).strip() or ('Tiroir refermé' if p.returncode==0 else 'Fermeture impossible')},200 if p.returncode==0 else 500)
            except Exception as e:self.api({'ok':False,'message':str(e)},500)
            return
        if route=='/api/stop':stop_all();self.api({'ok':True});return
        self.api({'error':'Route inconnue'},404)
    def stream(self,n):
        # A stream can be restarted at the beginning of any track. Seeking within
        # a track isn't supported because the CD is extracted live.
        stop_all()
        reader=None;encoder=None
        try:
            reader=subprocess.Popen(['cdparanoia','-q','-d',DEVICE,str(n),'-'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            encoder=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-i','pipe:0','-codec:a','libmp3lame','-b:a','320k','-f','mp3','pipe:1'],stdin=reader.stdout,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            reader.stdout.close()
            with state_lock:active.update((reader,encoder))
            self.send_response(200)
            self.send_header('Content-Type','audio/mpeg')
            self.send_header('Cache-Control','no-store, no-transform')
            self.send_header('Connection','close')
            self.end_headers()
            while True:
                piece=encoder.stdout.read(16384)
                if not piece:break
                self.wfile.write(piece);self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        except Exception as e:print('Streaming error:',repr(e),flush=True)
        finally:
            for p in (encoder,reader):
                if p:
                    with state_lock:active.discard(p)
                    try:p.terminate();p.wait(timeout=2)
                    except Exception:
                        try:p.kill()
                        except Exception:pass
            self.close_connection=True
    def log_message(self,fmt,*args):print('%s - %s'%(self.address_string(),fmt%args),flush=True)


def stop_all():
    with state_lock:old=list(active);active.clear()
    for p in old:
        try:p.terminate()
        except Exception:pass

if __name__=='__main__':
    print(f'Lecteur CD Web sur :{PORT}, périphérique {DEVICE}',flush=True)
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
