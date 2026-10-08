import {test} from 'node:test';
import assert from 'node:assert/strict';
import {calculatePlan} from './planning.js';
test('profit and break-even calculations',()=>{const r=calculatePlan({price:100,variableCost:40,units:100,fixedCost:3000});assert.equal(r.profit,3000);assert.equal(r.breakEven,50);assert.equal(r.margin,30);});
test('no break-even when contribution is not positive',()=>assert.equal(calculatePlan({price:10,variableCost:20,units:10,fixedCost:100}).breakEven,null));
test('invalid values are rejected',()=>{assert.throws(()=>calculatePlan({price:-1,variableCost:0,units:1,fixedCost:0}));assert.throws(()=>calculatePlan({price:1,variableCost:0,units:1.5,fixedCost:0}));});
