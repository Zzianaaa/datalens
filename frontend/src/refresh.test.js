import {test} from 'node:test';
import assert from 'node:assert/strict';
import Library from './LibraryPanel.js';
import Metrics from './MetricsPanel.js';
import Work from './WorkPanel.js';
import Inventory from './InventoryPanel.js';
import Receivables from './ReceivablesPanel.js';
import Operations from './OperationsPanel.js';
import Payables from './PayablesPanel.js';
import Expenses from './ExpensesPanel.js';
import Sales from './SalesPanel.js';
import {reactive,nextTick} from 'vue';

test('panel refreshes recover from a failed read without stale errors',async()=>{
 const original=globalThis.fetch;
 try{
  for(const [panel,props,payload] of [[Library,{}, {projects:[],assets:[],reports:[]}],[Metrics,{active:false},{templates:[]}],[Work,{active:false},{tasks:[],goals:[],projects:[]}],[Inventory,{active:false},{reconciliation:[],orders:[],items:[],movements:[]}],[Receivables,{active:false},{invoices:[],receipts:[]}]]){
   const state=panel.setup(props,{emit(){}});
   globalThis.fetch=async()=>{throw Error('临时读取失败');};
   await state.refresh();assert.equal(state.error.value,'临时读取失败');
   globalThis.fetch=async()=>({ok:true,json:async()=>payload});
   await state.refresh();assert.equal(state.error.value,'');
  }
 }finally{globalThis.fetch=original;}
});


test('a failed mutation clears a prior success notice',async()=>{
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async()=>{throw Error('保存失败');};
  for(const [panel,props,action] of [[Library,{},'create'],[Work,{active:false},'saveTask'],[Inventory,{active:false},'create'],[Receivables,{active:false},'create']]){
   const state=panel.setup(props,{emit(){}});
   state.notice.value='之前操作成功';
   state[action]();
   await new Promise(resolve=>setImmediate(resolve));
   assert.equal(state.notice.value,'');
   assert.ok(state.error.value);
   assert.equal(state.busy.value,false);
  }
 }finally{globalThis.fetch=original;}
});


test('failed metric save and archive clear previous success notices',async()=>{
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async()=>({ok:false,json:async()=>({detail:'请求失败'})});
  const state=Metrics.setup({active:false},{emit(){}});
  state.notice.value='之前保存成功';await state.save();
  assert.equal(state.notice.value,'');assert.ok(state.error.value);assert.equal(state.busy.value,false);
  state.notice.value='之前归档成功';await state.archive({id:'qa',archived:false});
  assert.equal(state.notice.value,'');assert.ok(state.error.value);assert.equal(state.busy.value,false);
 }finally{globalThis.fetch=original;}
});


test('old dataset request errors do not appear on a newly selected dataset',async()=>{
 const original=globalThis.fetch;
 try{
  for(const action of ['calculate','clean']){
   const props=reactive({dataset:{id:'old',columns:[]}});
   const state=Operations.setup(props,{emit(){}});
   let rejectRequest;globalThis.fetch=()=>new Promise((resolve,reject)=>{rejectRequest=reject;});
   const pending=state[action](true);
   props.dataset={id:'new',columns:[]};await nextTick();
   rejectRequest(Error('旧数据请求失败'));await pending;
   assert.equal(state.error.value,'');assert.equal(state.busy.value,false);
  }
 }finally{globalThis.fetch=original;}
});


test('operations clear old success notices on dataset changes and failed requests',async()=>{
 const original=globalThis.fetch;
 try{
  const props=reactive({dataset:{id:'old',columns:[]}});
  const state=Operations.setup(props,{emit(){}});
  state.notice.value='之前清洗成功';
  props.dataset={id:'new',columns:[]};await nextTick();
  assert.equal(state.notice.value,'');
  globalThis.fetch=async()=>{throw Error('当前操作失败');};
  for(const action of ['calculate','clean']){
   state.notice.value='之前操作成功';await state[action](true);
   assert.equal(state.notice.value,'');assert.equal(state.error.value,'当前操作失败');
   assert.equal(state.busy.value,false);
  }
 }finally{globalThis.fetch=original;}
});


test('clean success survives parent dataset update but not an unrelated switch',async()=>{
 const original=globalThis.fetch;
 try{
  for(const unrelated of [false,true]){
   const props=reactive({dataset:{id:'old',columns:[]}});
   const state=Operations.setup(props,{emit:(event,data)=>{props.dataset=unrelated?{id:'other',columns:[]}:data;}});
   globalThis.fetch=async()=>({ok:true,json:async()=>({dataset:{id:'cleaned',columns:[]}})});
   await state.clean(false);
   assert.equal(state.error.value,'');assert.equal(state.busy.value,false);
   if(unrelated)assert.equal(state.notice.value,'');
   else{assert.match(state.notice.value,/已生成清洗副本/);props.dataset={id:'next',columns:[]};await nextTick();assert.equal(state.notice.value,'');}
  }
 }finally{globalThis.fetch=original;}
});


test('payment retries retain token until payment details change',async()=>{
 const original=globalThis.fetch;
 try{
  const requests=[];
  globalThis.fetch=async(path,options)=>{requests.push(JSON.parse(options.body));throw Error('响应丢失');};
  const state=Payables.setup({active:false},{emit(){}});
  state.billId.value='bill-1';state.amount.value='1.23';state.note.value='说明';
  const pay=async()=>{state.pay();await new Promise(resolve=>setImmediate(resolve));};
  await pay();await pay();assert.equal(requests[0].payment_id,requests[1].payment_id);
  for(const [field,value] of [['amount','1.24'],['note','新说明'],['billId','bill-2']]){
   const previous=requests.at(-1).payment_id;state[field].value=value;await pay();
   assert.notEqual(requests.at(-1).payment_id,previous);
  }
  assert.equal(requests.at(-1).amount,124);assert.equal(state.busy.value,false);
  assert.equal(state.amount.value,'1.24');assert.equal(state.note.value,'新说明');
 }finally{globalThis.fetch=original;}
});


test('expense retry identity follows all saved expense fields',async()=>{
 const original=globalThis.fetch;
 try{
  const requests=[];globalThis.fetch=async(path,options)=>{requests.push(JSON.parse(options.body));throw Error('响应丢失');};
  const state=Expenses.setup({active:false});
  state.reference.value='QA';state.amount.value='1.23';state.occurred.value='2026-10-19';
  const save=async()=>{state.create();await new Promise(resolve=>setImmediate(resolve));};
  await save();await save();assert.equal(requests[0].expense_id,requests[1].expense_id);
  for(const [field,value] of [['reference','QA-2'],['category','软件'],['amount','1.24'],['occurred','2026-10-20'],['counterparty','虚构商户'],['projectId','qa-project'],['note','新说明']]){
   const previous=requests.at(-1).expense_id;state[field].value=value;await save();
   assert.notEqual(requests.at(-1).expense_id,previous,field);
  }
  assert.equal(requests.at(-1).amount,124);assert.equal(state.busy.value,false);
 }finally{globalThis.fetch=original;}
});


test('arrival and shipment retry identities follow quantities',async()=>{
 const original=globalThis.fetch;
 try{
  for(const kind of ['arrival','shipment']){
   const requests=[];globalThis.fetch=async(path,options)=>{requests.push(JSON.parse(options.body));throw Error('响应丢失');};
   const state=(kind==='arrival'?Inventory:Sales).setup({active:false},{emit(){}});
   const order={id:'qa-order',lines:[{id:'line-1'},{id:'line-2'}]};
   const set=n=>{if(kind==='arrival')state.receiptQty.value[order.id]=String(n);else state.shipQty.value['line-1']=String(n);};
   const submit=async()=>{state[kind==='arrival'?'receive':'ship'](order);await new Promise(resolve=>setImmediate(resolve));};
   set(1);await submit();await submit();
   const field=kind==='arrival'?'receipt_id':'shipment_id';
   assert.equal(requests[0][field],requests[1][field]);
   set(2);await submit();assert.notEqual(requests[2][field],requests[1][field],kind);
   await submit();assert.equal(requests[3][field],requests[2][field]);
   if(kind==='shipment'){state.shipQty.value['line-2']='1';await submit();assert.notEqual(requests[4][field],requests[3][field]);}
   assert.equal(state.busy.value,false);
  }
 }finally{globalThis.fetch=original;}
});
