import hashlib,json,pathlib,sys,datetime,os,re,subprocess
from native import BASE,FIXED,NEW,NEGATIVE

def cases(report,listing=False):
    out={}
    def walk(s,parent=()):
        path=parent+(s.get('title',''),)
        for spec in s.get('specs',[]):
            for t in spec['tests']:
                key=(spec['file'],*path,spec['title'],t.get('projectName',''))
                assert key not in out,('duplicate case',key)
                results=t.get('results',[])
                if listing:out[key]=None;continue
                assert len(results)==1,('retry/missing result',key)
                v=results[0];assert v['status'] in ['passed','failed','skipped'],('error/timedout',key)
                if v['status'] in ['passed','skipped']:assert not v.get('errors'),('unexpected result error',key)
                out[key]={'status':v['status'],'annotations':t.get('annotations',[]),'errors':v.get('errors',[])}
        for c in s.get('suites',[]):walk(c,path)
    assert not report.get('errors'),report.get('errors')
    for s in report['suites']:walk(s)
    assert out
    return out

def listing_filename(name):
    return 'regression-list.json' if name=='regressions' else name+'-list.json'

def load(d):
    r=json.loads((d/'receipt.json').read_text());assert r['harness_hashes']=={f:hashlib.sha256((pathlib.Path(__file__).parent/f).read_bytes()).hexdigest() for f in ['native.py','compare.py','expected-trees.json','offlineReceipt.spec.ts','test_compare.py']};assert r['status']=='RAW_COLLECTION_COMPLETE';assert r['head']==({'baseline':BASE,'fixed':FIXED}[r['phase']]);assert r['source_before']==r['source_after']
    assert r['platform'] in ['Linux','Windows']
    assert r['machine']==({'Linux':'x86_64','Windows':'AMD64'}[r['platform']])
    assert r['harness_head']==os.environ['GITHUB_SHA'] and re.fullmatch('[0-9a-f]{40}',r['harness_head'])
    assert r['harness_tree']==os.environ['PLEXO_EXPECTED_HARNESS_TREE'] and re.fullmatch('[0-9a-f]{40}',r['harness_tree'])
    assert r['workflow_sha256']==os.environ['PLEXO_EXPECTED_WORKFLOW_SHA256']
    source_path=pathlib.PureWindowsPath(r['source_root']) if r['platform']=='Windows' else pathlib.PurePosixPath(r['source_root'])
    assert source_path.is_absolute() and source_path.name=='source'
    assert r['python']=='3.13.9'
    executable=pathlib.PureWindowsPath(r['python_executable']) if r['platform']=='Windows' else pathlib.PurePosixPath(r['python_executable']);assert executable.is_absolute()
    commands={}
    for c in r['commands']:
        assert c['name'] not in commands;commands[c['name']]=c
        assert c['cwd']==r['source_root'],('cwd drift',c['name'])
        start=datetime.datetime.fromisoformat(c['start_utc']);end=datetime.datetime.fromisoformat(c['end_utc'])
        assert start.utcoffset()==end.utcoffset()==datetime.timedelta(0), 'timestamps must be aware UTC'
        assert c['end_monotonic']>=c['start_monotonic'];assert end>=start;assert hashlib.sha256((d/(c['name']+'.log')).read_bytes()).hexdigest()==c['raw_sha256']
        assert c['exit']==(1 if c['name']=='regressions' and r['phase']=='baseline' else 0),(c['name'],c['exit'])
    assert (d/'node-version.log').read_text().strip()=='v22.19.0'
    assert (d/'npm-version.log').read_text().strip()=='10.9.3'
    assert (d/'python-version.log').read_text().strip()=='Python '+r['python']
    needed=['python-version','node-version','npm-version','install-static']
    if r['platform']=='Linux':needed+=['lint','typecheck','format','install-native','build','smoke-list','smoke','package','offline-receipt']+(['regression-list','regressions'] if r['phase']=='baseline' else [])
    else:needed+=['patch-native','torrent-list','torrent','sparse-list','sparse']
    assert list(commands)==needed
    npm='npm.cmd' if r['platform']=='Windows' else 'npm';npx='npx.cmd' if r['platform']=='Windows' else 'npx'
    argv={'python-version':[r['python_executable'],'--version'],'node-version':['node','--version'],'npm-version':[npm,'--version'],'install-static':[npm,'ci','--ignore-scripts'],'lint':[npm,'run','lint'],'typecheck':[npm,'run','typecheck'],'format':[npm,'run','format:check'],'install-native':[npm,'ci'],'build':[npm,'run','build'],'package':[npx,'electron-builder','--linux','dir','--publish','never'],'patch-native':[npx,'patch-package']}
    for name,c in commands.items():
        if name in argv: expected=argv[name]
        else:
            args=['e2e/offlineReceipt.spec.ts'] if name=='offline-receipt' else ['--grep','@smoke'] if name.startswith('smoke') else (['e2e/download.spec.ts','--grep','|'.join(map(re.escape,NEW))] if name.startswith('regression') else ['e2e/torrentNative.spec.ts' if name.startswith('torrent') else 'e2e/sparseFile.spec.ts'])
            if name.endswith('-list'):args+=['--list']
            expected=[npx,'playwright','test',*args,'--reporter=list,html,json']
            if name in ['smoke','regressions','offline-receipt']:expected=['xvfb-run','--auto-servernum','--server-args=-screen 0 1280x1024x24 -noreset',*expected]
        assert c['argv']==expected,('argv drift',name,c['argv'],expected)
    expected=json.loads((pathlib.Path(__file__).parent/'expected-trees.json').read_text())[r['head']]
    assert r['source_tree']==expected['tree']
    assert r['source_before']==expected['files']
    for name,item in r['source_before'].items():
        assert len(item['sha256'])==64 and len(item['git_blob'])==40 and item['mode'] in ['100644','100755','120000']
    assert len(r['source_before'])>100
    
    expected_reports=({'smoke-list.json','smoke.json','offline-receipt.json','offline-download.json'} | ({'regression-list.json','regressions.json'} if r['phase']=='baseline' else set())) if r['platform']=='Linux' else {'torrent-list.json','torrent.json','sparse-list.json','sparse.json'}
    assert set(r['report_hashes'])==expected_reports
    assert {f.name for f in d.glob('*.json') if f.name!='receipt.json'}==expected_reports
    for name,digest in r['report_hashes'].items():assert hashlib.sha256((d/name).read_bytes()).hexdigest()==digest,('report byte drift',name)
    def parsed(name):
        listing=cases(json.loads((d/listing_filename(name)).read_text()),True);actual=cases(json.loads((d/(name+'.json')).read_text()));assert listing.keys()==actual.keys();return actual
    return r,parsed

def check_windows_cases(rows):
    assert len(rows)==1 and all(v['status']=='passed' for v in rows.values()), 'Windows canonical test must PASS'

def bind_harness_context():
    harness=pathlib.Path(__file__).resolve().parent.parent
    def git(*args):return subprocess.check_output(['git','-C',str(harness),*args]).decode().strip()
    assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
    os.environ['PLEXO_EXPECTED_HARNESS_TREE']=git('rev-parse','HEAD^{tree}')
    os.environ['PLEXO_EXPECTED_WORKFLOW_SHA256']=hashlib.sha256((harness/'.github/workflows/plexo-native.yml').read_bytes()).hexdigest()

def main(p):
    bind_harness_context()
    receipt={}
    for osname in ['Linux','Windows']:
        b,bparse=load(p/f'{osname}-baseline');f,fparse=load(p/f'{osname}-fixed');assert b['platform']==f['platform']==osname
        assert b['python']==f['python'] and b['machine']==f['machine'] and b['harness_head']==f['harness_head'] and b['harness_tree']==f['harness_tree']
        for name in (['smoke'] if osname=='Linux' else ['torrent','sparse']):
            bc=bparse(name);fc=fparse(name)
            if osname=='Linux':
                from urllib.parse import urlsplit
                for phase,expected in [('baseline','test.bin'),('fixed','quarterly report.csv')]:
                    offline=json.loads((p/f'{osname}-{phase}'/'offline-download.json').read_text());assert urlsplit(offline['url']).hostname=='127.0.0.1';assert offline['bytes']==196608
                    assert offline['fileName']==expected,(phase,offline['fileName'])
                    assert offline['destinationPath'].startswith(offline['isolatedDirs']['dest'])
                    assert offline['versions']['electron']
                    assert offline['networks']['a']=='127.0.0.1'
                    evidence=cases(json.loads((p/f'{osname}-{phase}'/'offline-receipt.json').read_text()));assert len(evidence)==1 and next(iter(evidence.values()))['status']=='passed'

            if osname=='Linux':
                new={k:v for k,v in fc.items() if k[-2] in NEW};assert {k[-2] for k in new}==set(NEW) and len(new)==7
                assert all(v['status']=='passed' for v in new.values());fc={k:v for k,v in fc.items() if k not in new}
                regress=bparse('regressions');assert {k[-2] for k in regress}==set(NEW) and len(regress)==7
                assert {k[-2] for k,v in regress.items() if v['status']=='failed'}==set(NEGATIVE)
                assert all(v['status']==('failed' if k[-2] in NEGATIVE else 'passed') for k,v in regress.items())
                for key,value in regress.items():
                    if key[-2] in NEGATIVE:assert any('toMatch' in e.get('message','') and 'quarterly report' in e.get('message','') for e in value['errors']),('unexpected baseline failure',key)
            assert bc==fc,('original outcome/skip drift',osname,name)
            if osname=='Windows':check_windows_cases(bc)
            assert all(v['status'] in ['passed','skipped'] for v in bc.values())
            receipt[osname+'-'+name]={'originals':len(bc),'preserved_skips':sum(v['status']=='skipped' for v in bc.values())}
    print(json.dumps({'status':'PASS','inventories':receipt},indent=2))
if __name__=='__main__':main(pathlib.Path(sys.argv[1]))
