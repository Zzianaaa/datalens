import {test} from 'node:test';
import assert from 'node:assert/strict';
import Library from './LibraryPanel.js';
import Metrics from './MetricsPanel.js';

test('library and metric refresh recover from a failed read without stale errors',async()=>{
 const original=globalThis.fetch;
 try{
  for(const [panel,props,payload] of [[Library,{}, {projects:[],assets:[],reports:[]}],[Metrics,{active:false},{templates:[]}]]){
   const state=panel.setup(props,{emit(){}});
   globalThis.fetch=async()=>{throw Error('临时读取失败');};
   await state.refresh();assert.equal(state.error.value,'临时读取失败');
   globalThis.fetch=async()=>({ok:true,json:async()=>payload});
   await state.refresh();assert.equal(state.error.value,'');
  }
 }finally{globalThis.fetch=original;}
});
