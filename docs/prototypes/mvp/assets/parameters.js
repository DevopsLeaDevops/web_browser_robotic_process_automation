/* 離線原型參數引擎。完整 JSON Schema 驗證由 Python 執行端負責。 */
window.Parameters=(()=>{
  const copy=v=>JSON.parse(JSON.stringify(v)), fail=m=>{throw Error(m)};
  const types=s=>s.type?(Array.isArray(s.type)?s.type:[s.type]):[];
  function compatible(a,b){const x=types(a),y=types(b);return !x.length||!y.length||x.every(t=>y.includes(t)||(t==='integer'&&y.includes('number')))}
  function tokens(v,endpoint=null){
    if(Array.isArray(v))return v.map(x=>tokens(x,endpoint));
    if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,tokens(x,endpoint)]));
    if(typeof v!=='string')return v;
    const m=v.match(/^\{\{random:(\d+):(\d+)\}\}$/);
    if(m){const lo=+m[1],hi=+m[2];if(lo>hi||hi>1e9)fail('隨機數範圍無效');return endpoint==='min'?lo:endpoint==='max'?hi:lo+Math.floor(Math.random()*(hi-lo+1))}
    v=v.replace(/\{\{today([+-]\d+)?\}\}/g,(_,d)=>{const date=new Date();const day=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(date);const utc=new Date(day+'T00:00:00Z');utc.setUTCDate(utc.getUTCDate()+Number(d||0));return utc.toISOString().slice(0,10)});
    if(v.includes('{{')||v.includes('}}'))fail('存在未識別的參數占位符');return v;
  }
  function check(v,s,name='參數'){
    const match=t=>t==='null'?v===null:t==='array'?Array.isArray(v):t==='object'?v!==null&&typeof v==='object'&&!Array.isArray(v):t==='integer'?Number.isInteger(v):typeof v===t;
    if(types(s).length&&!types(s).some(match))fail(name+' 的型別不符');
    if(s.enum&&!s.enum.some(x=>JSON.stringify(x)===JSON.stringify(v)))fail(name+' 不在允許值中');
    if(typeof v==='number'&&(!Number.isFinite(v)||(s.minimum!==undefined&&v<s.minimum)||(s.maximum!==undefined&&v>s.maximum)))fail(name+' 超出允許範圍');
    if(typeof v==='string'&&((s.minLength!==undefined&&v.length<s.minLength)||(s.maxLength!==undefined&&v.length>s.maxLength)||(s.pattern&&!new RegExp(s.pattern).test(v))))fail(name+' 格式或長度不符');
    if(Array.isArray(v)){if(s.minItems!==undefined&&v.length<s.minItems)fail(name+' 項目不足');if(s.maxItems!==undefined&&v.length>s.maxItems)fail(name+' 項目過多');if(s.items)v.forEach((x,i)=>check(x,s.items,name+'['+i+']'))}
    if(v&&typeof v==='object'&&!Array.isArray(v)){for(const k of s.required||[])if(!Object.hasOwn(v,k))fail('缺少必填入參 '+k);for(const[k,x]of Object.entries(v)){if(s.properties?.[k])check(x,s.properties[k],k);else if(s.additionalProperties===false)fail('不支援的參數 '+k)}}return v;
  }
  function plan(node,graph,catalog){
    const s=catalog[node.sceneId];if(!s)fail('未知場景 '+node.sceneId);
    const fields=s.inputSchema.properties||{},parents=graph.edges.filter(e=>e.target===node.id).map(e=>e.source),bindings=node.bindings||{},result={};
    for(const key of Object.keys(bindings))if(!Object.hasOwn(fields,key))fail('入參欄位不存在 '+key);
    for(const[name,schema]of Object.entries(fields)){
      let b=bindings[name];
      if(!b){const sources=parents.filter(id=>{const n=graph.nodes.find(n=>n.id===id),f=catalog[n.sceneId].outputSchema.properties[name];return f&&compatible(f,schema)});if(sources.length>1)fail(name+' 有多個同名上游，請指定來源');b=sources.length?{kind:'output',source:sources[0],field:name}:{kind:'default'}}
      const keys={default:['kind'],value:['kind','value'],output:['kind','source','field']}[b.kind];
      if(!keys||keys.length!==Object.keys(b).length||keys.some(k=>!Object.hasOwn(b,k)))fail('參數綁定格式錯誤');
      if(b.kind==='output'){if(!parents.includes(b.source))fail(name+' 引用了未連接的上游');const n=graph.nodes.find(n=>n.id===b.source),f=catalog[n.sceneId].outputSchema.properties[b.field];if(!f||!compatible(f,schema))fail(name+' 的來源不存在或型別不相容')}
      result[name]=copy(b);
    }return result;
  }
  function resolve(scene,bindings,calls=null,endpoint=null){
    const values=copy(scene.defaults),deferred=[];
    for(const[name,b]of Object.entries(bindings)){if(b.kind==='output')delete values[name];else if(b.kind==='value')values[name]=copy(b.value)}
    const actual=tokens(values,endpoint);
    for(const[name,b]of Object.entries(bindings)){if(b.kind!=='output')continue;if(calls===null){deferred.push(name);continue}const u=[...calls].reverse().find(c=>c.nodeId===b.source&&c.status==='passed');if(!u||!u.outputs||!Object.hasOwn(u.outputs,b.field))fail(name+' 缺少實際上游出參；停止下游');actual[name]=copy(u.outputs[b.field])}
    const schema=copy(scene.inputSchema);schema.required=(schema.required||[]).filter(k=>!deferred.includes(k));check(actual,schema);return actual;
  }
  function prepare(graph,catalog){
    graph=copy(graph);catalog=copy(catalog);
    if((graph.parameterBindingVersion??1)!==1)fail('不支援的參數綁定版本，請升級執行器');
    if(!graph.nodes.length||graph.nodes.length>50)fail('工作流需包含 1–50 個節點');const ids=graph.nodes.map(n=>n.id);
    if(new Set(ids).size!==ids.length||ids.some(id=>!(/^[A-Za-z][A-Za-z0-9_-]{0,63}$/).test(id)))fail('節點編號無效或重複');let total=0;
    for(const n of graph.nodes){if(!catalog[n.sceneId]||catalog[n.sceneId].state!=='已發布')fail('場景必須已發布');if(!Number.isInteger(n.repeat)||n.repeat<1||n.repeat>1000)fail('執行次數須為 1–1000 的整數');total+=n.repeat}
    if(total>1000)fail('工作流最多執行 1000 次');const pairs=new Set();
    for(const e of graph.edges){const k=e.source+'>'+e.target;if(!ids.includes(e.source)||!ids.includes(e.target)||e.source===e.target||pairs.has(k))fail('連線無效或重複');pairs.add(k)}
    const order=[],remaining=new Set(ids);
    while(remaining.size){const ready=[...remaining].filter(id=>graph.edges.filter(e=>e.target===id).every(e=>order.includes(e.source)));if(!ready.length)fail('工作流包含循環');ready.forEach(id=>{order.push(id);remaining.delete(id)})}
    const plans={};for(const node of graph.nodes){const scene=catalog[node.sceneId];check(scene.example,scene.outputSchema);plans[node.id]=plan(node,graph,catalog);resolve(scene,plans[node.id],null,'min');resolve(scene,plans[node.id],null,'max')}
    return {graph,catalog,order,plans,total};
  }
  return {compatible,tokens,check,plan,resolve,prepare};
})();
