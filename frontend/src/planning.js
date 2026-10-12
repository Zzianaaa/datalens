export function planInput(value){if(value===null||value===undefined||String(value).trim()==='')throw Error('请完整填写经营假设');return Number(value);}
export function calculatePlan({price,variableCost,units,fixedCost}){
 for(const v of [price,variableCost,units,fixedCost])if(!Number.isFinite(v)||v<0)throw Error('请输入非负且有限的数值');
 if(!Number.isInteger(units))throw Error('销量必须是整数');
 const contribution=price-variableCost,revenue=price*units,cost=fixedCost+variableCost*units,profit=revenue-cost;
 if(![revenue,cost,profit].every(Number.isFinite))throw Error('数值过大，无法计算');
 const breakEven=contribution>0?Math.ceil(fixedCost/contribution):null,margin=revenue?profit/revenue*100:null;
 if((breakEven!==null&&!Number.isSafeInteger(breakEven))||(margin!==null&&!Number.isFinite(margin)))throw Error('数值比例过大，无法可靠计算');
 return {revenue,cost,profit,contribution,breakEven,margin};
}
