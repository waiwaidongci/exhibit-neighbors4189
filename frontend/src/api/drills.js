import {api} from './client.js';
export const drillsApi={
  list:()=>api('/drills'),
  create:data=>api('/drills',{method:'POST',body:JSON.stringify(data)}),
  get:id=>api('/drills/'+id),
  start:id=>api('/drills/'+id+'/start',{method:'POST'}),
  retry:id=>api('/drills/'+id+'/retry',{method:'POST'}),
  overlap:id=>api('/drills/'+id+'/overlap'),
  research:(id,limit=200)=>api('/drills/'+id+'/research-copy?limit='+limit),
};
