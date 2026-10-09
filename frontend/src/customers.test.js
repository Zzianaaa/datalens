import test from 'node:test';
import assert from 'node:assert/strict';
import {customerSummary} from './customers.js';
test('customer totals preserve cents and prioritize overdue balances',()=>{
 const rows=[{customer:'A',amount:10001,paid:4000,due:'2026-10-08'},{customer:'A',amount:2000,paid:2000,due:'2026-01-01'},{customer:'B',amount:9000,paid:0,due:'2026-10-09'}];
 const [a,b]=customerSummary(rows,'2026-10-09');assert.equal(a.customer,'A');assert.equal(a.unpaid,6001);assert.equal(a.overdue,6001);assert.deepEqual(a.buckets,[0,6001,0,0,0]);assert.equal(a.rate,6000/12001);assert.equal(b.overdue,0);
});
test('aging boundaries and exact customer grouping',()=>{
 const day='2026-10-09',due=['2026-10-09','2026-09-09','2026-09-08','2026-08-10','2026-08-09','2026-07-11','2026-07-10'];
 const rows=due.map(d=>({customer:'A',amount:100,paid:0,due:d}));rows.push({customer:'AA',amount:1,paid:0,due:day});const summary=customerSummary(rows,day);assert.deepEqual(summary[0].buckets,[100,100,200,200,100]);assert.equal(summary.length,2);assert.deepEqual(customerSummary([],day),[]);
});


import {supplierSummary} from './InventoryPanel.js';
test('supplier procurement preserves quantities and cents and excludes closed orders',()=>{
 const base={supplier:'供应商 A',status:'open',ordered:5,received:2,due:'2026-10-10',unit_cost:1001,item_id:'a',sku:'A',unit:'件'};
 const rows=supplierSummary([base,{...base,ordered:4,received:1,due:'2026-10-09'}, {...base,item_id:'b',sku:'B',unit:'箱',unit_cost:0,due:''},{...base,status:'cancelled'},{...base,status:'complete'},{...base,received:5}], '2026-10-10');
 assert.equal(rows.length,1);assert.equal(rows[0].orders,3);assert.equal(rows[0].overdue,1);assert.equal(rows[0].unscheduled,1);assert.equal(rows[0].knownCost,6006);assert.equal(rows[0].unknownCost,1);assert.equal(rows[0].earliest,'2026-10-09');assert.deepEqual(rows[0].items,[{sku:'A',unit:'件',quantity:6},{sku:'B',unit:'箱',quantity:3}]);
});
test('supplier grouping is exact and prioritizes overdue orders',()=>{
 const base={status:'open',ordered:1,received:0,unit_cost:0,item_id:'a',sku:'A',unit:'件'};
 const rows=supplierSummary([{...base,supplier:'A',due:''},{...base,supplier:'a',due:'2026-10-09'}],'2026-10-10');
 assert.deepEqual(rows.map(r=>r.supplier),['a','A']);assert.deepEqual(supplierSummary([],'2026-10-10'),[]);
});
