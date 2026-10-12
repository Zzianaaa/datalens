import {test} from 'node:test';
import assert from 'node:assert/strict';
import {numericColumns,chartOption} from './chart.js';
const r={columns:['类别','数量','金额'],rows:[['a',2,10],['b',3,null]]};
test('chart supports selected columns and missing values',()=>{assert.deepEqual(numericColumns(r).map(x=>x.index),[1,2]);assert.deepEqual(chartOption(r,0,2).series[0].data,[10]);});
test('pie refuses negative values',()=>assert.throws(()=>chartOption({columns:['x','y'],rows:[['a',-1]]},0,1,'pie'),/负数/));
test('chart is bounded to 50 items',()=>assert.equal(chartOption({columns:['x','y'],rows:Array.from({length:80},(_,i)=>[String(i),i])},0,1).series[0].data.length,50));
test('all-null columns are not chartable',()=>assert.deepEqual(numericColumns({columns:['empty'],rows:[[null]]}),[]));

test('pie validates negatives beyond display limit and rejects all zero slices',()=>{const r={columns:['类别','值'],rows:[...Array.from({length:50},(_,i)=>[String(i),1]),['尾行',-1]]};assert.throws(()=>chartOption(r,0,1,'pie'));assert.throws(()=>chartOption({columns:r.columns,rows:[['零',0]]},0,1,'pie'));assert.ok(chartOption({columns:r.columns,rows:[['零',0]]},0,1,'bar'));});
