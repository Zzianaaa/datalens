export const quoteIdentifier = name => '"'+name.replaceAll('"','""')+'"';
export function sqlTemplates(columns, numericName, categoryName){
 const templates=[{label:'预览前 10 行',sql:'SELECT * FROM data LIMIT 10'},{label:'统计总行数',sql:'SELECT COUNT(*) AS "总行数" FROM data'}];
 const number=columns.find(c=>c.type==='DOUBLE'&&c.name===numericName)||columns.find(c=>c.type==='DOUBLE');
 const category=columns.find(c=>c.type==='VARCHAR'&&c.name===categoryName)||columns.find(c=>c.type==='VARCHAR');
 if(number){const n=quoteIdentifier(number.name);templates.push({label:'数值汇总 · '+number.name,sql:`SELECT MIN(${n}) AS "最小值", MAX(${n}) AS "最大值", AVG(${n}) AS "平均值", SUM(${n}) AS "合计" FROM data`});}
 if(category){const c=quoteIdentifier(category.name);templates.push({label:'分组计数 · '+category.name,sql:`SELECT ${c}, COUNT(*) AS "数量" FROM data GROUP BY ${c} ORDER BY "数量" DESC LIMIT 10`});}
 if(category&&number){const c=quoteIdentifier(category.name),n=quoteIdentifier(number.name);templates.push({label:'分组汇总 · '+number.name,sql:`SELECT ${c}, SUM(${n}) AS "合计" FROM data GROUP BY ${c} ORDER BY "合计" DESC LIMIT 10`});}
 return templates;
}
