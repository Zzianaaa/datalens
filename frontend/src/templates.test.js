import {test} from 'node:test';
import assert from 'node:assert/strict';
import {quoteIdentifier,sqlTemplates} from './templates.js';
test('identifiers are safely quoted',()=>assert.equal(quoteIdentifier('x"y'),'"x""y"'));
test('templates work without numeric fields',()=>assert.equal(sqlTemplates([{name:'类别',type:'VARCHAR'}]).length,3));
test('numeric and categorical templates use current schema',()=>{const ts=sqlTemplates([{name:'商品 类别',type:'VARCHAR'},{name:'金额',type:'DOUBLE'}]);assert.equal(ts.length,5);assert.ok(ts[4].sql.includes('SUM("金额")'));assert.ok(ts[4].sql.includes('GROUP BY "商品 类别"'));});
test('selected fields determine grouping template',()=>{const ts=sqlTemplates([{name:'a',type:'DOUBLE'},{name:'b',type:'DOUBLE'},{name:'x',type:'VARCHAR'},{name:'y',type:'VARCHAR'}],'b','y');assert.ok(ts[4].sql.includes('SUM("b")'));assert.ok(ts[4].sql.includes('GROUP BY "y"'));});
