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
