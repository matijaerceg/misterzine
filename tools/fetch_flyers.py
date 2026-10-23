#!/usr/bin/env python3
"""Fetch catalogue-matched flyers from the MAME 0.279 EXTRAs public archive.

Uses HTTP Range and the nested ZIP directory, not a 62 GB archive download.
Requires requests. Run with --output pointing to scratch space outside the repo.
The source ZIP contains 5,123 PNGs (pack dated 2023-03-31); the fixed offset was
verified against the tar header. Every fetched PNG is size/CRC checked. Existing
valid downloads are reused. Full ZIP index and selection/provenance are saved.
Original artwork remains property of the respective publishers.
"""
import requests,io,zipfile,json
from pathlib import Path
URL='https://archive.org/download/mame_extras-0.279/mame_extras-0.279.tar'
BASE=15208146432
SIZE=7637210837
class Remote(io.RawIOBase):
 def __init__(self): self.pos=0; self.s=requests.Session()
 def seekable(self): return True
 def seek(self,o,w=0):
  self.pos = o if w==0 else self.pos+o if w==1 else SIZE+o
  return self.pos
 def tell(self): return self.pos
 def read(self,n=-1):
  if n<0: n=SIZE-self.pos
  if not n:return b''
  a=BASE+self.pos; r=self.s.get(URL,headers={'Range':f'bytes={a}-{a+n-1}'},timeout=90); r.raise_for_status()
  assert r.status_code==206 and len(r.content)==n,(r.status_code,len(r.content),n)
  self.pos+=n; return r.content

import concurrent.futures,struct,zlib,time,hashlib
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--catalogue',type=Path,default=Path(__file__).resolve().parents[1]/'docs/releases/data.json')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
ROOT=args.output
ROOT.mkdir(parents=True,exist_ok=True)
rows=json.loads(args.catalogue.read_text(encoding='utf8'))
keys={r.get(f) for r in rows if r.get('base')=='Arcade' for f in ('sn','family')} - {None,''}
z=zipfile.ZipFile(Remote()); members=[i for i in z.infolist() if Path(i.filename).stem in keys]
out=ROOT/'source';out.mkdir(exist_ok=True)
(ROOT/'zip-members.json').write_text(json.dumps([{'name':i.filename,'size':i.file_size,'compressed':i.compress_size,'offset':i.header_offset} for i in z.infolist()],indent=2))
(ROOT/'provenance.json').write_text(json.dumps({'archive_url':URL,'member':'flyers/flyers.zip','member_offset':BASE,'member_bytes':SIZE,'selection':'Exact Arcade sn/family matches only; no fuzzy matching.','validation':'ZIP size and CRC32 for each file.'},indent=2))
(ROOT/'selection.json').write_text(json.dumps({'archive_count':len(z.infolist()),'wanted_count':len(keys),'selected_count':len(members),'missing':sorted(keys-{Path(i.filename).stem for i in members})},indent=2))
print('Selected',len(members),'bytes',sum(i.compress_size for i in members),flush=True)
def fetch(i):
 p=out/Path(i.filename).name
 if p.exists() and p.stat().st_size==i.file_size and zlib.crc32(p.read_bytes())==i.CRC:return
 for attempt in range(5):
  try:
   a=BASE+i.header_offset;n=30+len(i.filename.encode())+len(i.extra)+i.compress_size+1024
   r=requests.get(URL,headers={'Range':f'bytes={a}-{a+n-1}'},timeout=90);r.raise_for_status(); assert r.status_code==206
   h=r.content; assert h[:4]==b'PK\x03\x04'; nl,el=struct.unpack_from('<HH',h,26); comp=h[30+nl+el:30+nl+el+i.compress_size]
   data=zlib.decompress(comp,-15) if i.compress_type==8 else comp
   assert len(data)==i.file_size and zlib.crc32(data)==i.CRC
   p.write_bytes(data); return
  except Exception:
   if attempt==4:raise
   time.sleep(2*(attempt+1))
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
 for count,_ in enumerate(pool.map(fetch,members),1):
  if count%25==0:print(count,'/',len(members),flush=True)
print('DONE',len(members),flush=True)
