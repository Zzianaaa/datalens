import {test} from 'node:test';
import assert from 'node:assert/strict';
import {csvCell,resultCSV} from './export.js';
test('quotes and newlines are escaped',()=>assert.equal(csvCell('a,"b"\nc'),'"a,""b""\nc"'));
test('text formulas are escaped',()=>assert.equal(csvCell(' =SUM(A1)'), '"\' =SUM(A1)"'));
test('numeric negatives remain numeric',()=>assert.equal(csvCell(-12),'"-12"'));
test('CSV includes headers and empty values',()=>assert.equal(resultCSV({columns:['a','b'],rows:[[1,null]]}),'\uFEFF"a","b"\r\n"1",'));
