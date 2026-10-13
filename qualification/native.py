"""Fork-only actual canonical Plexo gates. No credentials or external test services."""
import argparse, datetime, hashlib, json, os, pathlib, platform, re, subprocess, time, sys
BASE='5366a8c01c68b53a1d5fcc04cdad41e53444d37f'
FIXED='c0b19a0122edba1a9352800b84ed3fdad8361ad8'
NEW=['a quoted filename keeps priority over an earlier duplicate token','malformed earlier extended values do not hide a usable filename star','a filename parameter accepts optional whitespace','an unrelated parameter does not shadow filename','a quoted extension value does not shadow filename star','an ordinary quoted filename is preserved','a UTF-8 filename star is decoded']
NEGATIVE=NEW[2:5]
def sha(b):return hashlib.sha256(b).hexdigest()
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args])
def snapshot(root):
    result={}
    for raw in git(root,'ls-tree','-r','-z','HEAD').split(b'\0'):
        if not raw:continue
        meta,name=raw.split(b'\t');mode,kind,oid=meta.decode().split();name=name.decode();p=root/name
        assert kind=='blob',('unexpected gitlink',name)
        expected=git(root,'cat-file','blob',oid)
        actual=os.readlink(p).encode() if mode=='120000' else p.read_bytes()
        assert actual==expected,('tracked source drift',name)
        if os.name!='nt' and mode!='120000':assert bool(p.stat().st_mode&0o111)==(mode=='100755'),name
        result[name]={'mode':mode,'git_blob':oid,'sha256':sha(actual)}
    assert not git(root,'status','--porcelain','--untracked-files=no').strip()
    return result

def main():
    a=argparse.ArgumentParser();a.add_argument('--source',required=True);a.add_argument('--proof',required=True);a.add_argument('--phase',choices=['baseline','fixed'],required=True);x=a.parse_args()
    root=pathlib.Path(x.source).resolve();proof=pathlib.Path(x.proof).resolve();proof.mkdir(parents=True,exist_ok=True)
    system=platform.system();assert system in ['Linux','Windows'];head=git(root,'rev-parse','HEAD').decode().strip();assert head==({'baseline':BASE,'fixed':FIXED}[x.phase])
    harness=pathlib.Path(__file__).resolve().parent.parent;harness_head=git(harness,'rev-parse','HEAD').decode().strip();assert harness_head==os.environ['GITHUB_SHA']
    r={'source_root':str(root),'source_tree':git(root,'rev-parse','HEAD^{tree}').decode().strip(),'harness_head':harness_head,'harness_tree':git(harness,'rev-parse','HEAD^{tree}').decode().strip(),'workflow_sha256':sha((harness/'.github/workflows/plexo-native.yml').read_bytes()),'python_executable':sys.executable,'status':'INCOMPLETE','phase':x.phase,'head':head,'platform':system,'python':platform.python_version(),'machine':platform.machine(),'harness_hashes':{f:sha((pathlib.Path(__file__).parent/f).read_bytes()) for f in ['native.py','compare.py','expected-trees.json','offlineReceipt.spec.ts','test_compare.py']},'commands':[],'source_before':snapshot(root)}
    def run(name,argv,extra=None):
        env=os.environ.copy();env.update(extra or {});start=time.monotonic();utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (proof/(name+'.log')).open('wb') as f:
            try:code=subprocess.run(argv,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,shell=False).returncode
            except OSError as e:f.write(str(e).encode());code=127
        r['commands'].append({'name':name,'argv':argv,'cwd':str(root),'exit':code,'start_utc':utc,'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'start_monotonic':start,'end_monotonic':time.monotonic(),'raw_sha256':sha((proof/(name+'.log')).read_bytes())});return code
    npm='npm.cmd' if system=='Windows' else 'npm';npx='npx.cmd' if system=='Windows' else 'npx'
    def tests(name,args,display=False):
        output=proof/(name+'.json');argv=[npx,'playwright','test',*args,'--reporter=list,html,json']
        if display:argv=['xvfb-run','--auto-servernum','--server-args=-screen 0 1280x1024x24 -noreset',*argv]
        return run(name,argv,{'PLAYWRIGHT_JSON_OUTPUT_NAME':str(output),'PLAYWRIGHT_HTML_OUTPUT_DIR':str(proof/(name+'-html')),'PLAYWRIGHT_HTML_OPEN':'never'})
    original=None
    try:
        run('python-version',[sys.executable,'--version']);run('node-version',['node','--version']);run('npm-version',[npm,'--version'])
        run('install-static',[npm,'ci','--ignore-scripts'])
        if system=='Linux':
            run('lint',[npm,'run','lint']);run('typecheck',[npm,'run','typecheck']);run('format',[npm,'run','format:check'])
            run('install-native',[npm,'ci']);run('build',[npm,'run','build'])
            tests('smoke-list',['--grep','@smoke','--list'])
            tests('smoke',['--grep','@smoke'],True)
            run('package',[npx,'electron-builder','--linux','dir','--publish','never'])
            diagnostic=root/'e2e/offlineReceipt.spec.ts';assert not diagnostic.exists()
            diagnostic.write_bytes((pathlib.Path(__file__).parent/'offlineReceipt.spec.ts').read_bytes())
            try:
                os.environ['PLEXO_QUALIFICATION_PROOF']=str(proof)
                tests('offline-receipt',['e2e/offlineReceipt.spec.ts'],True)
            finally:diagnostic.unlink()
            if x.phase=='baseline':
                p=root/'e2e/download.spec.ts';original=p.read_bytes();p.write_bytes(git(root,'cat-file','blob',FIXED+':e2e/download.spec.ts'))
                tests('regression-list',['e2e/download.spec.ts','--grep','|'.join(map(re.escape,NEW)),'--list'])
                tests('regressions',['e2e/download.spec.ts','--grep','|'.join(map(re.escape,NEW))],True)
                p.write_bytes(original);original=None
        else:
            run('patch-native',[npx,'patch-package'])
            os.environ['PLEXO_E2E_SKIP_BUILD']='1'
            for name,file in [('torrent','e2e/torrentNative.spec.ts'),('sparse','e2e/sparseFile.spec.ts')]:
                tests(name+'-list',[file,'--list']);tests(name,[file])
        r['report_hashes']={f.name:sha(f.read_bytes()) for f in proof.glob('*.json') if f.name!='receipt.json'}
        r['source_after']=snapshot(root);assert r['source_before']==r['source_after'];r['status']='RAW_COLLECTION_COMPLETE'
    finally:
        if original is not None:(root/'e2e/download.spec.ts').write_bytes(original)
        (proof/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
