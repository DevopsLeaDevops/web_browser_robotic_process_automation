"""參數與執行回歸；真實測試僅訪問隨附的本機測試頁。"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from contracts import scene_catalog
from workflow_parameters import prepare_workflow, resolve, compatible
from run_workflow import run_workflow

BASE=Path(__file__).resolve().parent

def graph(): return json.loads((BASE/'examples/workflow.json').read_text(encoding='utf-8'))

class ParameterTests(unittest.TestCase):
    def test_auto_and_fixed_different_field(self):
        p=prepare_workflow(graph(),scene_catalog())
        self.assertEqual(p['plans']['verify']['recordId'],{'kind':'output','source':'create','field':'recordId'})
        self.assertEqual(p['plans']['verify']['expectedTitle']['field'],'title')

    def test_manual_preserves_catalog_default(self):
        g=graph();c=scene_catalog();g['nodes'][1]['bindings']['quantity']={'kind':'value','value':23}
        p=prepare_workflow(g,c)
        self.assertEqual(resolve(p['contracts']['verify'],p['plans']['verify'])['quantity'],23)
        self.assertEqual(c['BA-002']['input']['defaults']['quantity'],12)

    def test_explicit_default_ignores_upstream(self):
        g=graph();g['nodes'][1]['bindings']['recordId']={'kind':'default'}
        p=prepare_workflow(g,scene_catalog())
        self.assertEqual(resolve(p['contracts']['verify'],p['plans']['verify'])['recordId'],'DEMO-001')

    def test_last_successful_actual_output(self):
        p=prepare_workflow(graph(),scene_catalog())
        calls=[{'nodeId':'create','status':'passed','outputs':{'recordId':'DEMO-A','title':'第一筆','quantity':10}},
               {'nodeId':'create','status':'passed','outputs':{'recordId':'DEMO-B','title':'第二筆','quantity':23}}]
        r=resolve(p['contracts']['verify'],p['plans']['verify'],calls)
        self.assertEqual((r['recordId'],r['quantity'],r['expectedTitle']),('DEMO-B',23,'第二筆'))

    def test_missing_last_field_never_falls_back(self):
        p=prepare_workflow(graph(),scene_catalog())
        calls=[{'nodeId':'create','status':'passed','outputs':{'recordId':'DEMO-A','title':'第一筆','quantity':10}},
               {'nodeId':'create','status':'passed','outputs':{'recordId':'DEMO-B'}}]
        with self.assertRaisesRegex(ValueError,'缺少'): resolve(p['contracts']['verify'],p['plans']['verify'],calls)

    def test_upstream_text_is_literal(self):
        p=prepare_workflow(graph(),scene_catalog())
        calls=[{'nodeId':'create','status':'passed','outputs':{'recordId':'DEMO-A','title':'{{today}}','quantity':10}}]
        self.assertEqual(resolve(p['contracts']['verify'],p['plans']['verify'],calls)['expectedTitle'],'{{today}}')

    def test_conflict_requires_explicit_source(self):
        g=graph();g['nodes'].append({**deepcopy(g['nodes'][0]),'id':'another'});g['edges'].append({'source':'another','target':'verify'})
        with self.assertRaisesRegex(ValueError,'多個同名'):prepare_workflow(g,scene_catalog())
        for f in ['recordId','quantity']:g['nodes'][1]['bindings'][f]={'kind':'output','source':'create','field':f}
        self.assertEqual(prepare_workflow(g,scene_catalog())['plans']['verify']['recordId']['source'],'create')

    def test_unknown_source_field_and_type_are_rejected(self):
        for b in [{'kind':'output','source':'missing','field':'title'}, {'kind':'output','source':'create','field':'missing'}, {'kind':'output','source':'create','field':'quantity'}]:
            g=graph();g['nodes'][1]['bindings']['expectedTitle']=b
            with self.subTest(b=b),self.assertRaises(ValueError):prepare_workflow(g,scene_catalog())

    def test_integer_can_flow_into_number(self):
        self.assertTrue(compatible({'type':'integer'},{'type':'number'}))
        self.assertFalse(compatible({'type':'number'},{'type':'integer'}))

    def test_unknown_binding_version_is_rejected(self):
        g=graph();g['parameterBindingVersion']=2
        with self.assertRaisesRegex(ValueError,'綁定版本'):prepare_workflow(g,scene_catalog())

    def test_cycle_and_repeat_limit(self):
        g=graph();g['edges'].append({'source':'verify','target':'create'})
        with self.assertRaisesRegex(ValueError,'循環'):prepare_workflow(g,scene_catalog())
        g=graph();g['nodes'][0]['repeat']=1000
        with self.assertRaisesRegex(ValueError,'1000'):prepare_workflow(g,scene_catalog())

    def test_snapshots_do_not_mutate_after_start(self):
        g=graph();c=scene_catalog();p=prepare_workflow(g,c)
        c['BA-001']['input']['defaults']['title']='新版';g['nodes'][0]['repeat']=7
        self.assertEqual(p['contracts']['create']['input']['defaults']['title'],'介面驗證範例')
        self.assertEqual(p['graph']['nodes'][0]['repeat'],2)

    def test_placeholders_resolve_before_validation(self):
        g=graph();g['nodes'][0]['bindings']={'quantity':{'kind':'value','value':'{{random:10:30}}'},'title':{'kind':'value','value':'紀錄 {{today+1}}'}}
        p=prepare_workflow(g,scene_catalog());actual=resolve(p['contracts']['create'],p['plans']['create'])
        self.assertTrue(10<=actual['quantity']<=30);self.assertNotIn('{{',actual['title'])
        g['nodes'][0]['bindings']['quantity']['value']='{{random:10:50}}'
        with self.assertRaises(Exception):prepare_workflow(g,scene_catalog())

    def test_missing_required_or_invalid_value_blocks_all_actions(self):
        for binding in [{'quantity':{'kind':'value','value':99}}, {'quantity':{'kind':'value','value':'oops'}}]:
            g=graph();g['nodes'][0]['bindings']=binding;executor=Mock()
            with tempfile.TemporaryDirectory() as d,self.assertRaises(Exception):run_workflow(g,d,executor=executor)
            executor.assert_not_called()
        c=scene_catalog();del c['BA-001']['input']['defaults']['title']
        with self.assertRaises(Exception):prepare_workflow(graph(),c)

    def test_typed_arrays_objects_boolean_and_null(self):
        schema={'type':'object','required':['items','meta','enabled','empty'],'additionalProperties':False,'properties':{'items':{'type':'array','items':{'type':'integer'}},'meta':{'type':'object'},'enabled':{'type':'boolean'},'empty':{'type':['string','null']}}}
        values={'items':[1,2],'meta':{'n':3},'enabled':False,'empty':None}
        contract={'input':{'schema':schema,'defaults':values}}
        self.assertEqual(resolve(contract,{k:{'kind':'value','value':v} for k,v in values.items()}),values)

    def test_legacy_workflow_without_bindings(self):
        g=graph()
        for n in g['nodes']:n.pop('bindings')
        self.assertEqual(prepare_workflow(g,scene_catalog())['plans']['verify']['recordId']['source'],'create')

    def test_runtime_schema_failure_stops_downstream(self):
        calls=[]
        def executor(scene,inputs,url,folder,*args,**kw):
            calls.append(scene);f=folder/('fake-'+str(len(calls)));f.mkdir()
            return {'runId':f.name,'status':'passed','output':{'recordId':'DEMO-A','title':'標題','quantity':99}},f
        with tempfile.TemporaryDirectory() as d:
            result,_=run_workflow(graph(),d,executor=executor)
        self.assertEqual(result['status'],'failed');self.assertEqual(calls,['BA-001','BA-001'])

    def test_failure_iteration_does_not_start_downstream(self):
        calls=[]
        def executor(scene,inputs,url,folder,*args,**kw):
            calls.append(scene);f=folder/('fake-'+str(len(calls)));f.mkdir()
            return {'runId':f.name,'status':'failed','output':None,'error':'範例失敗'},f
        with tempfile.TemporaryDirectory() as d:r,_=run_workflow(graph(),d,executor=executor)
        self.assertEqual(r['status'],'failed');self.assertEqual(calls,['BA-001'])

    def test_real_browser_last_output_and_reports(self):
        with tempfile.TemporaryDirectory() as d:
            result,folder=run_workflow(graph(),d)
            self.assertEqual(result['status'],'passed',result.get('error'))
            a,b,verify=result['calls']
            self.assertNotEqual(a['outputs']['recordId'],b['outputs']['recordId'])
            self.assertEqual(verify['inputs']['recordId'],b['outputs']['recordId'])
            self.assertEqual(verify['inputs']['expectedTitle'],b['outputs']['title'])
            self.assertEqual(verify['sources']['recordId'],b['runId'])
            self.assertEqual(verify['outputs'],b['outputs'])
            self.assertTrue((folder/'workflow-snapshot.json').is_file())
            report=(folder/verify['report']).read_text(encoding='utf-8')
            self.assertIn('參數來源快照',report)
            self.assertTrue((folder/verify['runId']/'output.json').is_file())

if __name__=='__main__':unittest.main()
