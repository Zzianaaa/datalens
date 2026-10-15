export function planInput(value){if(value===null||value===undefined||String(value).trim()==='')throw Error('请完整填写经营假设');return Number(value);}
export function calculatePlan({price,variableCost,units,fixedCost}){
 for(const v of [price,variableCost,units,fixedCost])if(!Number.isFinite(v)||v<0)throw Error('请输入非负且有限的数值');
 if(!Number.isSafeInteger(units))throw Error('销量必须是安全范围内的整数');
 const contribution=price-variableCost,revenue=price*units,cost=fixedCost+variableCost*units,profit=revenue-cost;
 if(![revenue,cost,profit].every(Number.isFinite))throw Error('数值过大，无法计算');
 let breakEven=contribution>0?Math.ceil(fixedCost/contribution):null;
 const margin=revenue?profit/revenue*100:null;
 if((breakEven!==null&&!Number.isSafeInteger(breakEven))||(margin!==null&&!Number.isFinite(margin)))throw Error('数值比例过大，无法可靠计算');
 // Verify the adjacent lower volume with the same revenue/cost arithmetic used above.
 if(breakEven!==null&&breakEven>0){const lower=breakEven-1,lowerRevenue=lower*price,lowerCost=fixedCost+lower*variableCost;if(Number.isFinite(lowerRevenue)&&Number.isFinite(lowerCost)&&lowerRevenue>=lowerCost)breakEven=lower;}
 return {revenue,cost,profit,contribution,breakEven,margin};
}
