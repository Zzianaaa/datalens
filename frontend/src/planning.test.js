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
