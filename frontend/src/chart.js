export function numericColumns(result){return result.columns.map((name,index)=>({name,index})).filter(c=>result.rows.some(r=>typeof r[c.index]==='number'&&Number.isFinite(r[c.index]))&&result.rows.every(r=>r[c.index]==null||(typeof r[c.index]==='number'&&Number.isFinite(r[c.index]))));}
export function chartOption(result,xIndex,yIndex,type='bar'){
 if(!numericColumns(result).some(c=>c.index===yIndex)||!result.columns[xIndex])return null;
 const rows=result.rows.filter(r=>r[yIndex]!=null).slice(0,50);
 const data=rows.map(r=>r[yIndex]);
 if(type==='pie'&&result.rows.some(r=>r[yIndex]!=null&&r[yIndex]<0))throw Error('饼图不支持负数，请使用柱状图或折线图');
 if(type==='pie'&&!data.some(v=>v>0))throw Error('饼图需要至少一个正数，请使用柱状图或折线图');
 const base={animation:false,tooltip:{trigger:type==='pie'?'item':'axis'},color:['#287c66','#69a48c','#bdd3c2','#e3bc76','#758ca2']};
 if(type==='pie')return {...base,series:[{type:'pie',radius:['35%','65%'],data:rows.map(r=>({name:String(r[xIndex]??'缺失'),value:r[yIndex]}))}]};
 return {...base,grid:{left:65,right:30,top:30,bottom:65},xAxis:{type:'category',name:result.columns[xIndex],data:rows.map(r=>String(r[xIndex]??'缺失')),axisLabel:{rotate:rows.length>6?25:0}},yAxis:{type:'value',name:result.columns[yIndex]},series:[{type,data,itemStyle:{color:'#287c66'},lineStyle:{width:3}}]};
}
