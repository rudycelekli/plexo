import copy,unittest,json,pathlib,tempfile,hashlib,os,subprocess,shutil,importlib.util,re
from compare import load,BASE
from native import NEW
from compare import cases,check_windows_cases,listing_filename

def report(status='passed'):
    return {'suites':[{'title':'e2e/download.spec.ts','specs':[{'title':'actual case','file':'e2e/download.spec.ts','tests':[{'projectName':'','annotations':[],'results':[{'status':status,'errors':[]}]}]}]}]}
class Controls(unittest.TestCase):
    def test_baseline_regression_list_name(self):
        self.assertEqual(listing_filename('regressions'),'regression-list.json')
        self.assertNotEqual(listing_filename('regressions'),'regressions-list.json')
        self.assertEqual(listing_filename('smoke'),'smoke-list.json')
    def test_actual_pass(self):self.assertEqual(next(iter(cases(report()).values()))['status'],'passed')
    def test_missing_result(self):
        r=report();r['suites'][0]['specs'][0]['tests'][0]['results']=[]
        with self.assertRaises(AssertionError):cases(r)
    def test_retry(self):
        r=report();r['suites'][0]['specs'][0]['tests'][0]['results']*=2
        with self.assertRaises(AssertionError):cases(r)
    def test_error_status(self):
        with self.assertRaises(AssertionError):cases(report('timedOut'))
    def test_empty_inventory(self):
        with self.assertRaises(AssertionError):cases({'suites':[]})
    def test_duplicate(self):
        r=report();r['suites'][0]['specs']*=2
        with self.assertRaises(AssertionError):cases(r)
    def test_passed_with_error(self):
        r=report();r['suites'][0]['specs'][0]['tests'][0]['results'][0]['errors']=[{'message':'compiler error'}]
        with self.assertRaises(AssertionError):cases(r)
    def test_global_error(self):
        r=report();r['errors']=[{'message':'compiler failure'}]
        with self.assertRaises(AssertionError):cases(r)
    def test_skip_reason_is_preserved(self):
        a=report('skipped');b=copy.deepcopy(a);b['suites'][0]['specs'][0]['tests'][0]['annotations']=[{'type':'skip','description':'LAN unavailable'}]
        self.assertNotEqual(cases(a),cases(b))
    def test_inventory_identity_drift(self):
        a=report();b=copy.deepcopy(a);b['suites'][0]['specs'][0]['title']='omitted original'
        self.assertNotEqual(cases(a).keys(),cases(b).keys())
class ReceiptControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.d=pathlib.Path(self.tmp.name)
        tree=json.loads((pathlib.Path(__file__).parent/'expected-trees.json').read_text())[BASE]
        source=copy.deepcopy(tree['files'])
        self.old_workflow_env=os.environ.get('PLEXO_EXPECTED_WORKFLOW_SHA256');os.environ['PLEXO_EXPECTED_WORKFLOW_SHA256']=hashlib.sha256((pathlib.Path(__file__).parent/'plexo-native.yml').read_bytes()).hexdigest();self.old_env=os.environ.get('GITHUB_SHA');self.old_tree_env=os.environ.get('PLEXO_EXPECTED_HARNESS_TREE');os.environ['GITHUB_SHA']='a'*40;os.environ['PLEXO_EXPECTED_HARNESS_TREE']='b'*40
        args=[('python-version',['C:/Python313/python.exe','--version']),('node-version',['node','--version']),('npm-version',['npm.cmd','--version']),('install-static',['npm.cmd','ci','--ignore-scripts']),('patch-native',['npx.cmd','patch-package'])]
        for n,f in [('torrent','e2e/torrentNative.spec.ts'),('sparse','e2e/sparseFile.spec.ts')]:
            args.extend([(n+'-list',['npx.cmd','playwright','test',f,'--list','--reporter=list,html,json']),(n,['npx.cmd','playwright','test',f,'--reporter=list,html,json'])])
        commands=[]
        for n,a in args:
            b=(('Python 3.13.9' if n=='python-version' else 'v22.19.0' if n=='node-version' else '10.9.3' if n=='npm-version' else '')+'\n').encode();(self.d/(n+'.log')).write_bytes(b)
            commands.append({'name':n,'argv':a,'cwd':'D:/a/plexo/plexo/source','exit':0,'start_utc':'2026-10-13T00:00:00+00:00','end_utc':'2026-10-13T00:00:01+00:00','start_monotonic':1,'end_monotonic':2,'raw_sha256':hashlib.sha256(b).hexdigest()})
        reports={}
        for name in ['torrent-list.json','torrent.json','sparse-list.json','sparse.json']:
            b=json.dumps(report()).encode();(self.d/name).write_bytes(b);reports[name]=hashlib.sha256(b).hexdigest()
        self.r={'source_root':'D:/a/plexo/plexo/source','source_tree':tree['tree'],'python':'3.13.9','python_executable':'C:/Python313/python.exe','machine':'AMD64','harness_head':'a'*40,'harness_tree':'b'*40,'workflow_sha256':hashlib.sha256((pathlib.Path(__file__).parent/'plexo-native.yml').read_bytes()).hexdigest(),'report_hashes':reports,'harness_hashes':{f:hashlib.sha256((pathlib.Path(__file__).parent/f).read_bytes()).hexdigest() for f in ['native.py','compare.py','expected-trees.json','offlineReceipt.spec.ts','test_compare.py']},'status':'RAW_COLLECTION_COMPLETE','head':BASE,'phase':'baseline','platform':'Windows','source_before':source,'source_after':copy.deepcopy(source),'commands':commands}
    def tearDown(self):
        self.tmp.cleanup()
        if self.old_env is None:os.environ.pop('GITHUB_SHA',None)
        else:os.environ['GITHUB_SHA']=self.old_env
        if self.old_tree_env is None:os.environ.pop('PLEXO_EXPECTED_HARNESS_TREE',None)
        else:os.environ['PLEXO_EXPECTED_HARNESS_TREE']=self.old_tree_env
        if self.old_workflow_env is None:os.environ.pop('PLEXO_EXPECTED_WORKFLOW_SHA256',None)
        else:os.environ['PLEXO_EXPECTED_WORKFLOW_SHA256']=self.old_workflow_env
    def write(self): (self.d/'receipt.json').write_text(json.dumps(self.r))
    def rejected(self):
        self.write()
        with self.assertRaises(AssertionError):load(self.d)
    def test_complete_receipt_control(self):self.write();load(self.d)
    def test_changed_argv(self):self.r['commands'][2]['argv'].append('--force');self.rejected()
    def test_missing_command(self):self.r['commands'].pop();self.rejected()
    def test_duplicate_command(self):self.r['commands'].append(self.r['commands'][0]);self.rejected()
    def test_failed_required_command(self):self.r['commands'][2]['exit']=1;self.rejected()
    def test_raw_hash_drift(self):self.r['commands'][0]['raw_sha256']='f'*64;self.rejected()
    def test_clock_reversal(self):self.r['commands'][0]['end_monotonic']=0;self.rejected()
    def test_source_blob_drift(self):
        key=next(iter(self.r['source_before']))
        for phase in ['source_before','source_after']:self.r[phase][key]['git_blob']='f'*40
        self.rejected()
    def test_version_drift(self):
        b=b'v22.20.0\n';(self.d/'node-version.log').write_bytes(b);self.r['commands'][1]['raw_sha256']=hashlib.sha256(b).hexdigest();self.rejected()
    def test_partial_receipt(self):self.r['status']='INCOMPLETE';self.rejected()
    def test_actual_deployed_Git_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);q=root/'qualification';q.mkdir();workflow=root/'.github/workflows/plexo-native.yml';workflow.parent.mkdir(parents=True)
            local=pathlib.Path(__file__).parent
            helpers=['native.py','compare.py','expected-trees.json','offlineReceipt.spec.ts','test_compare.py']
            for name in helpers:shutil.copy2(local/name,q/name)
            shutil.copy2(local/'plexo-native.yml',workflow)
            self.assertFalse((q/'plexo-native.yml').exists())
            def git(*args):return subprocess.check_output(['git','-C',str(root),*args]).decode().strip()
            git('init','-q');git('add','.');git('-c','user.name=Qualification Control','-c','user.email=control@example.invalid','commit','-qm','actual deployed layout control')
            expected_paths={'.github/workflows/plexo-native.yml',*['qualification/'+n for n in helpers]}
            self.assertEqual(set(git('ls-tree','-r','--name-only','HEAD').splitlines()),expected_paths)
            for path in expected_paths:
                actual=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+path]);self.assertEqual(hashlib.sha256(actual).hexdigest(),hashlib.sha256((root/path).read_bytes()).hexdigest())
            spec=importlib.util.spec_from_file_location('deployed_plexo_compare',q/'compare.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            os.environ['GITHUB_SHA']=git('rev-parse','HEAD');self.r['harness_head']=os.environ['GITHUB_SHA'];self.r['harness_tree']=git('rev-parse','HEAD^{tree}')
            module.bind_harness_context();self.assertEqual(os.environ['PLEXO_EXPECTED_WORKFLOW_SHA256'],hashlib.sha256(workflow.read_bytes()).hexdigest())
            self.write();module.load(self.d)
            # Synthetic receipt contract; real Git deployment, canonical collector filenames.
            # This unit control is not a native app qualification result.
            self.make_linux_receipt();self.write();_,parsed=module.load(self.d)
            rows=parsed('regressions');self.assertEqual(len(rows),7)
            list_file=self.d/'regression-list.json';saved=list_file.read_bytes();list_file.unlink()
            with self.assertRaises(FileNotFoundError):parsed('regressions')
            (self.d/'regressions-list.json').write_bytes(saved)
            with self.assertRaises(FileNotFoundError):parsed('regressions')
            (self.d/'regressions-list.json').unlink();list_file.write_bytes(saved)
            self.assertEqual(len(parsed('regressions')),7)
    def make_linux_receipt(self):
        for name in ['torrent-list.json','torrent.json','sparse-list.json','sparse.json']:(self.d/name).unlink()
        root='/home/runner/work/plexo/plexo/source';python='/opt/python/bin/python'
        self.r.update(platform='Linux',machine='x86_64',source_root=root,python_executable=python)
        args=[('python-version',[python,'--version']),('node-version',['node','--version']),('npm-version',['npm','--version']),('install-static',['npm','ci','--ignore-scripts'])]
        args += [(n,['npm','run',a]) for n,a in [('lint','lint'),('typecheck','typecheck'),('format','format:check')]]
        args += [('install-native',['npm','ci']),('build',['npm','run','build'])]
        display=['xvfb-run','--auto-servernum','--server-args=-screen 0 1280x1024x24 -noreset']
        reporter=['--reporter=list,html,json'];grep='|'.join(map(re.escape,NEW))
        args += [('smoke-list',['npx','playwright','test','--grep','@smoke','--list',*reporter]),('smoke',[*display,'npx','playwright','test','--grep','@smoke',*reporter]),('package',['npx','electron-builder','--linux','dir','--publish','never']),('offline-receipt',[*display,'npx','playwright','test','e2e/offlineReceipt.spec.ts',*reporter]),('regression-list',['npx','playwright','test','e2e/download.spec.ts','--grep',grep,'--list',*reporter]),('regressions',[*display,'npx','playwright','test','e2e/download.spec.ts','--grep',grep,*reporter])]
        commands=[]
        for name,argv in args:
            b=(('Python 3.13.9' if name=='python-version' else 'v22.19.0' if name=='node-version' else '10.9.3' if name=='npm-version' else '')+'\n').encode();(self.d/(name+'.log')).write_bytes(b)
            commands.append({'name':name,'argv':argv,'cwd':root,'exit':1 if name=='regressions' else 0,'start_utc':'2026-10-13T00:00:00+00:00','end_utc':'2026-10-13T00:00:01+00:00','start_monotonic':1,'end_monotonic':2,'raw_sha256':hashlib.sha256(b).hexdigest()})
        self.r['commands']=commands;reports={}
        for name in ['smoke-list.json','smoke.json','offline-receipt.json','offline-download.json','regression-list.json','regressions.json']:
            data=report()
            if name.startswith('regression'):
                data['suites'][0]['specs']=[{**copy.deepcopy(data['suites'][0]['specs'][0]),'title':title} for title in NEW]
            b=json.dumps(data).encode()
            if name in ['regression-list.json','regressions.json'] and os.environ.get('PLEXO_CONTROL_RAW_PAIR_DIR'):
                b=(pathlib.Path(os.environ['PLEXO_CONTROL_RAW_PAIR_DIR'])/name).read_bytes()
            (self.d/name).write_bytes(b);reports[name]=hashlib.sha256(b).hexdigest()
        self.r['report_hashes']=reports
    def test_wrong_cwd(self):self.r['commands'][2]['cwd']='D:/other/source';self.rejected()
    def test_wrong_source_root(self):self.r['source_root']='relative/source';self.rejected()
    def test_wrong_head(self):self.r['head']='f'*40;self.rejected()
    def test_wrong_harness_head(self):self.r['harness_head']='f'*40;self.rejected()
    def test_wrong_harness_tree(self):self.r['harness_tree']='f'*40;self.rejected()
    def test_wrong_machine(self):self.r['machine']='aarch64';self.rejected()
    def test_relative_python_executable(self):self.r['python_executable']='python';self.r['commands'][0]['argv']=['python','--version'];self.rejected()
    def test_wrong_python_runtime(self):self.r['python']='3.8.10';self.rejected()
    def test_wrong_workflow(self):self.r['workflow_sha256']='f'*64;self.rejected()
    def test_wrong_tree(self):self.r['source_tree']='f'*40;self.rejected()
    def test_naive_time(self):
        c=self.r['commands'][0];c['start_utc']='2026-10-13T00:00:00';c['end_utc']='2026-10-13T00:00:01';self.rejected()
    def test_nonUTC_time(self):
        c=self.r['commands'][0];c['start_utc']='2026-10-13T00:00:00+01:00';c['end_utc']='2026-10-13T00:00:01+01:00';self.rejected()
    def test_source_SHA_drift(self):
        key=next(iter(self.r['source_before']))
        for phase in ['source_before','source_after']:self.r[phase][key]['sha256']='0'*64
        self.rejected()
    def test_altered_report(self):(self.d/'torrent.json').write_text('{}');self.rejected()
    def test_wrong_report_hash(self):self.r['report_hashes']['torrent.json']='f'*64;self.rejected()
    def test_report_hash_swap(self):self.r['report_hashes']['torrent.json']='0'*64;self.rejected()
    def test_missing_report(self):self.r['report_hashes'].pop('torrent.json');self.rejected()
    def test_windows_same_skip_is_rejected(self):
        a=cases(report('skipped'));b=copy.deepcopy(a);self.assertEqual(a,b)
        with self.assertRaises(AssertionError):check_windows_cases(a)
    def test_windows_pass_control(self):check_windows_cases(cases(report()))
if __name__=='__main__':unittest.main(verbosity=2)
