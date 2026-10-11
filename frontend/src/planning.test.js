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

import {filterPurchaseOrders} from './InventoryPanel.js';
test('purchase filters combine supplier identity, partial receipt, deadline and search',()=>{
 const a={id:'PO-1',item_id:'i',sku:'SKU-1',name:'商品',supplier:'A',status:'open',ordered:5,received:2,due:'2026-10-09'};
 const orders=[a,{...a,supplier:'a'},{...a,received:0},{...a,status:'cancelled'},{...a,due:'2026-10-10'}];
 assert.deepEqual(filterPurchaseOrders(orders,{supplier:'A',status:'partial',deadline:'overdue',search:'sku-1',today:'2026-10-10'}),[a]);
 assert.equal(filterPurchaseOrders(orders,{deadline:'today',today:'2026-10-10'}).length,1);
 assert.equal(filterPurchaseOrders(orders,{search:'商品'}).length,5);
});
test('purchase undated deadline excludes closed and fully received orders',()=>{
 const a={id:'x',sku:'X',supplier:'B',status:'open',ordered:2,received:0,due:''};
 assert.deepEqual(filterPurchaseOrders([a,{...a,status:'complete'},{...a,status:'cancelled'},{...a,received:2}],{deadline:'undated',today:'2026-10-10'}),[a]);
 assert.deepEqual(filterPurchaseOrders([]),[]);assert.equal(filterPurchaseOrders([a],{search:' missing '}).length,0);
});

import {counterpartyExpenseSummary} from './ExpensesPanel.js';
test('counterparty expenses group exact names, preserve cents and exclude voids',()=>{
 const a={counterparty:'A',amount:1001,occurred:'2026-10-01',category:'软件'};
 const rows=counterpartyExpenseSummary([a,{...a,amount:2002,occurred:'2026-10-09',category:'营销'},{...a,counterparty:'a'},{...a,counterparty:''},{...a,amount:99999,void_reason:'误录'}]);
 assert.equal(rows.length,3);assert.equal(rows[0].amount,3003);assert.equal(rows[0].count,2);assert.equal(rows[0].first,'2026-10-01');assert.equal(rows[0].last,'2026-10-09');assert.deepEqual(rows[0].categories,[['营销',2002],['软件',1001]]);assert.equal(rows.find(r=>r.counterparty==='').amount,1001);
});
test('counterparty expense summary month boundaries and empty ranges',()=>{
 const a={counterparty:'A',amount:101,occurred:'2026-09-30',category:'软件'};
 assert.equal(counterpartyExpenseSummary([a,{...a,amount:202,occurred:'2026-10-01'}],'2026-10')[0].amount,202);
 assert.deepEqual(counterpartyExpenseSummary([a],'2026-11'),[]);assert.deepEqual(counterpartyExpenseSummary([]),[]);
});

import {budgetExecutionRows} from './ExpensesPanel.js';
test('budget execution includes unbudgeted expenses and excludes voids and other months',()=>{
 const a={category:'软件',amount:2001,occurred:'2026-10-01'};
 const rows=budgetExecutionRows([a,{...a,amount:9999,void_reason:'误录'},{...a,occurred:'2026-09-30'},{...a,category:'营销',amount:101}], [{month:'2026-10',category:'软件',amount:2500},{month:'2026-09',category:'营销',amount:50}],['软件','营销','办公'],'2026-10');
 const software=rows.find(r=>r.category==='软件');assert.equal(software.actual,2001);assert.equal(software.remaining,499);assert.equal(software.usage,80.04);
 assert.equal(rows.find(r=>r.category==='营销').limit,null);assert.equal(rows.find(r=>r.category==='办公').actual,0);
});
test('budget execution prioritizes overspending and keeps zero spending budget',()=>{
 const rows=budgetExecutionRows([{category:'软件',amount:101,occurred:'2026-10-10'}],[{month:'2026-10',category:'软件',amount:100},{month:'2026-10',category:'办公',amount:200}],[],'2026-10');
 assert.equal(rows[0].remaining,-1);assert.equal(rows[0].usage,101);assert.equal(rows[1].remaining,200);assert.equal(rows[1].usage,0);assert.deepEqual(budgetExecutionRows([],[],[],'2026-10'),[]);
});

test('budget execution does not present zero actuals for missing or invalid month',()=>{
 for(const month of ['',null,undefined,'2026-13','2026-00','2026-1'])assert.deepEqual(budgetExecutionRows([],[],['软件'],month),[]);
});

import {budgetDraft} from './ExpensesPanel.js';
test('budget draft preserves exact cents, clears unset limit and rejects missing month',()=>{
 assert.deepEqual(budgetDraft({category:'软件',limit:2501},'2026-10'),{month:'2026-10',category:'软件',amount:'25.01'});
 assert.equal(budgetDraft({category:'办公',limit:null},'2026-11').amount,'');
 assert.throws(()=>budgetDraft({category:'软件',limit:100},''));
});

import {filterAlerts} from './AlertsPanel.js';
test('alert search combines category and priority and searches detail case insensitively',()=>{
 const a={title:'付款任务',detail:'负责人 Alice',category:'任务',severity:'中'};
 assert.deepEqual(filterAlerts([a,{...a,severity:'高'},{...a,category:'付款'}],{category:'任务',severity:'中',search:' alice '}),[a]);
 assert.deepEqual(filterAlerts([a],{search:'missing'}),[]);assert.deepEqual(filterAlerts([]),[]);assert.equal(filterAlerts([a]).length,1);
});

import {arrivalSchedule} from './InventoryPanel.js';
test('arrival schedule groups open remaining costs and distinct suppliers by date',()=>{
 const base={status:'open',ordered:5,received:2,unit_cost:101,supplier:'A',due:'2026-10-11'};
 const rows=arrivalSchedule([base,{...base,supplier:'B',unit_cost:0},{...base,due:'2026-10-10'},{...base,due:''},{...base,due:'2026-10-12'},{...base,status:'cancelled'},{...base,received:5}],'2026-10-11');
 assert.deepEqual(rows.map(r=>r.key),['overdue','2026-10-11','2026-10-12','undated']);
 assert.equal(rows[1].label,'今天到货');assert.equal(rows[1].orders,2);assert.equal(rows[1].suppliers,2);assert.equal(rows[1].knownCost,303);assert.equal(rows[1].unknownCost,1);
 assert.deepEqual(arrivalSchedule([],'2026-10-11'),[]);
});

test('exact arrival date filter excludes closed and fully received purchases',()=>{
 const a={status:'open',ordered:5,received:2,due:'2026-10-12',supplier:'A',sku:'X'};
 assert.deepEqual(filterPurchaseOrders([a,{...a,due:'2026-10-13'},{...a,status:'cancelled'},{...a,received:5}],{arrivalDate:'2026-10-12'}),[a]);
 assert.deepEqual(filterPurchaseOrders([a],{arrivalDate:'2026-10-12',supplier:'B'}),[]);
});

import {pendingItemOrders} from './SalesPanel.js';
test('pending item orders use identity and exclude shipped lines and closed orders',()=>{
 const o={status:'partial',lines:[{item_id:'x',quantity:5,shipped:2}]};
 assert.deepEqual(pendingItemOrders([o,{...o,status:'cancelled'},{...o,status:'fulfilled'},{...o,lines:[{item_id:'x',quantity:5,shipped:5}]},{...o,lines:[{item_id:'y',quantity:5,shipped:2}]}],'x'),[o]);
 assert.deepEqual(pendingItemOrders([],'x'),[]);
});

import {fulfillmentExport} from './SalesPanel.js';
test('fulfillment export preserves units and distinguishes stock shortages from purchase gaps',()=>{
 const r={sku:'X',name:'商品',unit:'箱',orders:2,demand:10,stock:3,shortage:7,incoming:5,purchase_gap:2};
 const out=fulfillmentExport([r]);assert.equal(out.columns.length,9);assert.deepEqual(out.rows,[['X','商品','箱',2,10,3,7,5,2]]);assert.deepEqual(fulfillmentExport([]).rows,[]);
});
