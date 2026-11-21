export const drillStore={
  jobs:[],jobId:null,detail:null,overlap:null,research:null,
  reset(){this.jobs=[];this.jobId=null;this.detail=null;this.overlap=null;this.research=null;},
};
export const drillStates={
  sealed:'已封存',building:'构造中',failed:'中断待恢复',open:'已对账开放',
};
