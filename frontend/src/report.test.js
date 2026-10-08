import {test} from 'node:test';
import assert from 'node:assert/strict';
import {htmlReport,qualityCSV} from './report.js';
test('report escapes untrusted cells, headings and SQL',()=>{const h=htmlReport('<script>x</script>',{summary:'<img>',mode:'sql',sql:'SELECT "<x>"',columns:['<b>'],rows:[['<script>']]});assert.ok(!h.includes('<script>'));assert.ok(h.includes('&lt;script&gt;'));assert.ok(h.includes('SELECT &quot;'));});
test('quality CSV protects formula headers',()=>assert.ok(qualityCSV({columns:[{name:'=SUM(A1)',type:'VARCHAR',missing:0,missing_percent:0,distinct:1}]}).includes("'=SUM(A1)")));
