// Amounts stay in integer cents; customer names match exactly.
export function customerSummary(invoices,today){
 const grouped=new Map();
 for(const i of invoices){let c=grouped.get(i.customer);if(!c){c={customer:i.customer,count:0,amount:0,paid:0,unpaid:0,overdue:0,buckets:[0,0,0,0,0]};grouped.set(i.customer,c);}const balance=i.amount-i.paid;c.count++;c.amount+=i.amount;c.paid+=i.paid;c.unpaid+=balance;
 const days=Math.round((Date.parse(today+'T00:00:00Z')-Date.parse(i.due+'T00:00:00Z'))/86400000);const bucket=days<=0?0:days<=30?1:days<=60?2:days<=90?3:4;c.buckets[bucket]+=balance;if(days>0)c.overdue+=balance;
 }
 return [...grouped.values()].map(c=>({...c,rate:c.amount?c.paid/c.amount:0})).sort((a,b)=>b.overdue-a.overdue||b.unpaid-a.unpaid||a.customer.localeCompare(b.customer));
}
