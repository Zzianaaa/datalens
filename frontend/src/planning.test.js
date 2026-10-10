import {test} from 'node:test';
import assert from 'node:assert/strict';
import {calculatePlan} from './planning.js';
test('profit and break-even calculations',()=>{const r=calculatePlan({price:100,variableCost:40,units:100,fixedCost:3000});assert.equal(r.profit,3000);assert.equal(r.breakEven,50);assert.equal(r.margin,30);});
test('no break-even when contribution is not positive',()=>assert.equal(calculatePlan({price:10,variableCost:20,units:10,fixedCost:100}).breakEven,null));
test('invalid values are rejected',()=>{assert.throws(()=>calculatePlan({price:-1,variableCost:0,units:1,fixedCost:0}));assert.throws(()=>calculatePlan({price:1,variableCost:0,units:1.5,fixedCost:0}));});

import {projectExpenseSummary} from './ExpensesPanel.js';
test('project expense groups by identity, excludes voids, and preserves cents',()=>{
 const base={project_id:'p1',project_name:'同名项目',amount:1001,occurred:'2026-10-01',category:'软件',void_reason:null};
 const rows=projectExpenseSummary([base,{...base,amount:2002,occurred:'2026-10-09',category:'营销'},{...base,project_id:'p2'},{...base,project_id:null,project_name:null},{...base,void_reason:'误录',amount:99999}]);
 assert.equal(rows.length,3);assert.equal(rows[0].amount,3003);assert.equal(rows[0].count,2);assert.equal(rows[0].first,'2026-10-01');assert.equal(rows[0].last,'2026-10-09');assert.deepEqual(rows[0].categories,[['营销',2002],['软件',1001]]);assert.equal(rows.find(r=>r.id==='unassigned:').name,'未关联项目');
});
test('project expense month filtering and empty ranges',()=>{
 const rows=[{project_id:'p',project_name:'项目',amount:101,occurred:'2026-09-30',category:'软件'},{project_id:'p',project_name:'项目',amount:202,occurred:'2026-10-01',category:'软件'}];
 assert.equal(projectExpenseSummary(rows,'2026-10')[0].amount,202);assert.deepEqual(projectExpenseSummary(rows,'2026-11'),[]);assert.deepEqual(projectExpenseSummary([]),[]);
});

import {filterWorkTasks} from './WorkPanel.js';
test('task filters combine exact owner, project, text and open deadline state',()=>{
 const base={project_id:'p',owner:'A',title:'采购跟进',notes:'供应商',due:'2026-10-09',status:'待处理'};
 const tasks=[base,{...base,owner:'a'},{...base,status:'已完成'},{...base,status:'已归档'},{...base,project_id:'q'}];
 assert.deepEqual(filterWorkTasks(tasks,{project:'p',owner:'A',search:'供应商',deadline:'overdue',today:'2026-10-10'}),[base]);
 assert.equal(filterWorkTasks(tasks,{today:'2026-10-10'}).length,4);
 assert.equal(filterWorkTasks(tasks,{today:'2026-10-10',showArchive:true}).length,5);
});
test('task deadline today and unassigned undated exclude completed records',()=>{
 const base={project_id:null,owner:'',title:'付款',notes:'',due:'',status:'进行中'};
 const tasks=[base,{...base,due:'2026-10-10'},{...base,status:'已完成'}];
 assert.deepEqual(filterWorkTasks(tasks,{owner:'unassigned:',deadline:'undated',today:'2026-10-10'}),[base]);
 assert.equal(filterWorkTasks(tasks,{deadline:'today',today:'2026-10-10'}).length,1);
 assert.deepEqual(filterWorkTasks([],{today:'2026-10-10'}),[]);
});

import {replenishmentPlan} from './InventoryPanel.js';
test('replenishment nets partial open purchases by item identity and excludes closed remainder',()=>{
 const items=[{id:'a',sku:'A',name:'同名',unit:'件',quantity:2,reorder_level:10},{id:'b',sku:'B',name:'同名',unit:'箱',quantity:0,reorder_level:4}];
 const orders=[{item_id:'a',status:'open',ordered:8,received:3,due:'2026-10-09'},{item_id:'a',status:'open',ordered:3,received:1,due:''},{item_id:'a',status:'cancelled',ordered:100,received:0},{item_id:'a',status:'complete',ordered:2,received:2}];
 const rows=replenishmentPlan(items,orders,'2026-10-10');
 assert.equal(rows[0].id,'b');assert.equal(rows[0].additional,4);
 const a=rows.find(r=>r.id==='a');assert.equal(a.gap,8);assert.equal(a.incoming,7);assert.equal(a.additional,1);assert.equal(a.overdueIncoming,5);assert.equal(a.unscheduledIncoming,2);
 assert.equal(items[0].incoming,undefined);
});
test('replenishment coverage never adds negative quantities and today is not overdue',()=>{
 const items=[{id:'a',sku:'A',quantity:0,reorder_level:5},{id:'b',sku:'B',quantity:6,reorder_level:5},{id:'c',sku:'C',quantity:5,reorder_level:5}];
 const rows=replenishmentPlan(items,[{item_id:'a',status:'open',ordered:8,received:0,due:'2026-10-10'}],'2026-10-10');
 assert.equal(rows.length,2);assert.equal(rows[0].additional,0);assert.equal(rows[0].overdueIncoming,0);assert.equal(rows.find(r=>r.id==='c').gap,0);assert.deepEqual(replenishmentPlan([],[],'2026-10-10'),[]);
});
