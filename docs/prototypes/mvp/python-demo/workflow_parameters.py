"""通用參數管道：直接上游匹配、覆蓋、快照與實際出參校驗。"""
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import random
import re
from contracts import validate


def compatible(source, target):
    def types(schema):
        value = schema.get('type')
        return set(value if isinstance(value, list) else [value]) if value else set()
    a, b = types(source), types(target)
    return not a or not b or all(t in b or (t == 'integer' and 'number' in b) for t in a)


def clean_bindings(value):
    if not isinstance(value, dict) or len(json.dumps(value, allow_nan=False).encode()) > 100_000:
        raise ValueError('參數綁定必須為不超過 100 KB 的物件')
    allowed = {'default': {'kind'}, 'value': {'kind', 'value'}, 'output': {'kind', 'source', 'field'}}
    for name, binding in value.items():
        if not isinstance(name, str) or not isinstance(binding, dict):
            raise ValueError('參數綁定格式錯誤')
        kind = binding.get('kind')
        if not isinstance(kind, str) or kind not in allowed or set(binding) != allowed[kind]:
            raise ValueError('參數綁定僅支援 default、value、output')
        if kind == 'output' and any(not isinstance(binding[k], str) for k in ('source', 'field')):
            raise ValueError('來源節點與欄位必須為字串')
    return deepcopy(value)


def resolve_defaults(value, randint=None):
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    def visit(item):
        if isinstance(item, dict):
            return {key: visit(v) for key, v in item.items()}
        if isinstance(item, list):
            return [visit(v) for v in item]
        if not isinstance(item, str):
            return item
        match = re.fullmatch(r'\{\{random:(\d+):(\d+)\}\}', item)
        if match:
            low, high = map(int, match.groups())
            if not 0 <= low <= high <= 10**9:
                raise ValueError('隨機數範圍無效')
            return (randint or random.randint)(low, high)
        item = re.sub(r'\{\{today([+-]\d+)?\}\}', lambda m: (today+timedelta(days=int(m[1] or 0))).isoformat(), item)
        if '{{' in item or '}}' in item:
            raise ValueError('存在未識別的參數占位符')
        return item
    return visit(value)


def plan(node, graph, contracts):
    contract = contracts[node['id']]
    fields = contract['input']['schema'].get('properties', {})
    parents = [e['source'] for e in graph['edges'] if e['target'] == node['id']]
    explicit = clean_bindings(node.get('bindings', {}))
    if set(explicit)-set(fields):
        raise ValueError('入參欄位不存在：'+'、'.join(sorted(set(explicit)-set(fields))))
    bindings = {}
    for name, schema in fields.items():
        binding = explicit.get(name)
        if binding is None:
            candidates = [p for p in parents if name in contracts[p]['output']['schema'].get('properties', {})
                          and compatible(contracts[p]['output']['schema']['properties'][name], schema)]
            if len(candidates) > 1:
                raise ValueError(f'入參 {name} 有多個同名上游，請指定來源或固定值')
            binding = {'kind':'output','source':candidates[0],'field':name} if candidates else {'kind':'default'}
        if binding['kind'] == 'output':
            source = binding['source']
            if source not in parents:
                raise ValueError(f'入參 {name} 引用了未連接的上游節點')
            outputs = contracts[source]['output']['schema'].get('properties', {})
            if binding['field'] not in outputs:
                raise ValueError(f'入參 {name} 引用的出參欄位不存在')
            if not compatible(outputs[binding['field']], schema):
                raise ValueError(f'入參 {name} 與上游出參型別不相容')
        bindings[name] = deepcopy(binding)
    return bindings


def resolve(contract, bindings, calls=None, *, randint=None):
    requested = deepcopy(contract['input']['defaults'])
    for name, binding in bindings.items():
        if binding['kind'] == 'output':
            requested.pop(name, None)
        elif binding['kind'] == 'value':
            requested[name] = deepcopy(binding['value'])
    values = resolve_defaults(requested, randint=randint)
    deferred = []
    for name, binding in bindings.items():
        if binding['kind'] != 'output':
            continue
        if calls is None:
            deferred.append(name)
            continue
        upstream = [c for c in calls if c['nodeId'] == binding['source'] and c['status'] == 'passed']
        if not upstream or binding['field'] not in (upstream[-1].get('outputs') or {}):
            raise ValueError(f'入參 {name} 缺少上游 {binding["source"]} 的實際出參 {binding["field"]}；停止下游')
        values[name] = deepcopy(upstream[-1]['outputs'][binding['field']])
    schema = contract['input']['schema']
    if deferred:
        for name in schema.get('required', []):
            if name not in values and name not in deferred:
                raise ValueError(f'缺少必填入參 {name}')
        partial = {'type':'object','properties':schema.get('properties', {}),
                   'additionalProperties':schema.get('additionalProperties', True)}
        for name, value in values.items():
            validate({name:value}, partial)
    else:
        validate(values, schema)
    return values


def prepare_workflow(graph, catalog):
    """在第一個瀏覽器動作前固定全圖。分支以拓撲順序串行，不平行執行。"""
    graph = deepcopy(graph)
    if graph.get('parameterBindingVersion', 1) != 1:
        raise ValueError('不支援的參數綁定版本，請升級執行器')
    nodes, edges = graph.get('nodes', []), graph.get('edges', [])
    if not nodes or len(nodes) > 50:
        raise ValueError('工作流需包含 1–50 個節點')
    ids = [n['id'] for n in nodes]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', n) for n in ids):
        raise ValueError('節點編號必須唯一且格式有效')
    total = 0
    for node in nodes:
        if node['sceneId'] not in catalog:
            raise ValueError('未知場景')
        if type(node.get('repeat')) is not int or not 1 <= node['repeat'] <= 1000:
            raise ValueError('執行次數必須為 1–1000 的整數')
        total += node['repeat']
        node['bindings'] = clean_bindings(node.get('bindings', {}))
    if total > 1000:
        raise ValueError('每個工作流最多執行 1000 次')
    pairs = [(e['source'],e['target']) for e in edges]
    if len(pairs) != len(set(pairs)) or any(s not in ids or t not in ids or s == t for s,t in pairs):
        raise ValueError('連線包含重複、無效或自身引用')
    order, remaining = [], ids.copy()
    while remaining:
        ready = [n for n in remaining if all(s in order for s,t in pairs if t == n)]
        if not ready:
            raise ValueError('工作流包含循環')
        for node_id in ready:
            order.append(node_id);remaining.remove(node_id)
    contracts = {n['id']:deepcopy(catalog[n['sceneId']]) for n in nodes}
    plans = {}
    for node in nodes:
        contract = contracts[node['id']]
        validate(contract['output']['example'], contract['output']['schema'])
        plans[node['id']] = plan(node, graph, contracts)
        for choose in (min, max):
            resolve(contract, plans[node['id']], randint=choose)
    return {'graph':graph,'order':order,'contracts':contracts,'plans':plans,'total':total}
