import {drillStore,drillStates} from '../stores/drill.js';
import {session} from '../stores/session.js';
import {drillsApi} from '../api/drills.js';
import {table} from '../components/common/table.js';
import {metrics} from '../components/common/business.js';
import {esc,formObject,localTime} from '../utils/format.js';
import {action,toast,bind} from '../hooks/actions.js';

function drillStatus(state){
  const cls=state==='open'?'completed':state==='failed'?'failed':state==='building'?'running':'queued';
  return '<span class="status '+cls+'">'+esc(drillStates[state]||state)+'</span>';
}
function idempotencyHint(){
  const d=new Date();
  return 'DRILL-'+d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+Math.random().toString(36).slice(2,8).toUpperCase();
}

export async function drillPage(){
  drillStore.jobs=await drillsApi.list();
  if(!drillStore.jobId&&drillStore.jobs.length)drillStore.jobId=drillStore.jobs[0].id;
  drillStore.detail=drillStore.jobId?await drillsApi.get(drillStore.jobId):null;
  const j=drillStore.detail;
  let panel='<p class="empty">还没有演练。左侧受理一份封存原册，即可发起换号副本。</p>';
  if(j){
    const cert=j.result?.certificate;const recon=j.reconciliation;
    panel='<div class="run-title"><h2>'+esc(j.name)+'</h2>'+drillStatus(j.state)
      +'<small>#'+j.id+' · 受理号 '+esc(j.idempotency_key)+'</small></div>'
      +'<p class="fine">封存于 '+localTime(j.created_at)+' · 尝试 '+j.attempts+' 次 · 阶段 '+esc(j.stage)
      +'<br>封存快照 sha256 <code>'+esc(j.snapshot_sha256.slice(0,20))+'…</code>'
      +(j.published_at?' · 开放于 '+localTime(j.published_at):'')+'</p>'
      +(j.error?'<div class="failure"><h2>写入中断</h2><p>'+esc(j.error)+'</p><p class="fine">沿封存版本恢复，同受理号重试不会新增副本。</p></div>':'');

    if(j.state==='sealed'||j.state==='failed'){
      panel+=(session.writable?'<div class="entry-sheet"><h2>'+(j.state==='failed'?'恢复演练':'发起演练')+'</h2>'
        +'<p class="fine">系统按最小费用流求最少原配对复用，二百人规模为多项式时间，不穷举任何置换。</p>'
        +'<button id="drill-'+(j.state==='failed'?'retry':'start')+'">'+(j.state==='failed'?'沿封存版本重试恢复 →':'发起换号副本构造 →')+'</button></div>':'<p>当前为只读账号，无法发起演练。</p>');
    }
    if(cert){
      panel+='<h2>最少原配对复用 · 可核查依据</h2>'
        +metrics([
          {label:'封存评分总数 N',value:cert.total_ratings},
          {label:'非原边最大安排 M',value:cert.zero_edge_max_flow},
          {label:'最少复用 min',value:cert.min_reused},
          {label:'复用率',value:(cert.min_reused/cert.total_ratings).toFixed(4)},
        ])
        +'<div class="method-note"><b>最优性公式</b><p><code>'+esc(cert.formula)+'</code></p>'
        +'<p>'+esc(cert.min_cut_theorem)+'</p>'
        +'<p class="fine">'+esc(cert.model)+'；'+esc(cert.complexity)+'</p>'
        +'<p class="fine">独立校验：最小费用流 min_cost='+cert.min_cost+'，Dinic 最大流='+cert.dinic_independent_max_flow+'，最小割容量='+cert.min_cut_capacity+'，三者闭合。</p></div>';
    }
    if(recon){
      panel+='<h2>对账（全部通过才整批开放）</h2>'
        +table(recon.checks.map(c=>({item:c.item,passed:c.passed?'通过':'未过',detail:c.detail})),
          [{key:'item',label:'核对项'},{key:'passed',label:'结果'},{key:'detail',label:'依据'}],{limit:20});
    }
    if(j.state==='open'){
      panel+='<div class="split"><section><h2>重合数核对 <small>逐行可查</small></h2><div id="drill-overlap"><p class="fine">加载中…</p></div></section>'
        +'<aside class="entry-sheet"><h2>研究选用副本</h2><p class="fine">仅含换号后匿名编号、展品与星级，不含原编号；整批开放。</p>'
        +'<button id="drill-load-research" class="secondary">载入研究副本（前200条）</button><div id="drill-research"></div></aside></div>';
    }
  }
  return '<section class="page-heading"><p class="eyebrow">06 / RELOCATION DRILL</p><h1>迁展演练：换匿名号的评分副本。</h1>'
    +'<p>受理即封存原册（并发补录仍写原册、不进快照）；保留每人评分条数与每件展品各星级人数，同人同展品限一条；按最少原配对复用构造，对账通过才整批开放给研究选用。</p></section>'
    +'<div class="split"><section><label class="compact">演练任务<select id="drill-select">'
    +drillStore.jobs.map(x=>'<option value="'+x.id+'" '+(x.id==drillStore.jobId?'selected':'')+'>#'+x.id+' '+esc(x.name)+' · '+esc(drillStates[x.state]||x.state)+'</option>').join('')
    +'</select></label>'+panel+'</section><aside class="entry-sheet">'
    +(session.writable?'<h2>受理并封存原册</h2><form id="drill-form"><label>演练名称<input name="name" required value="十一月迁展演练"></label>'
      +'<label>受理号（幂等键，同号重试不新增副本）<input name="idempotency_key" required value="'+idempotencyHint()+'"></label>'
      +'<button type="submit">封存原册 →</button><p class="fine">封存后仍可向原册补录，但不影响本次快照。</p></form>'
      :'<h2>只读权限</h2><p>可查看演练、核对重合数与取用已开放副本；受理与发起由分析师或负责人完成。</p>')+'</aside></div>';
}

export function bindDrill(refresh){
  bind('#drill-select','change',async e=>{drillStore.jobId=Number(e.target.value);drillStore.overlap=null;drillStore.research=null;await refresh()});
  action('#drill-form',async form=>{
    const r=await drillsApi.create(formObject(form));
    drillStore.jobId=r.job.id;await refresh();
    toast(r.created?'原册已封存，可发起演练':'该受理号已存在，复用既有演练，未新增副本');
  });
  bind('#drill-start','click',async()=>{try{await drillsApi.start(drillStore.jobId);await refresh();toast('演练完成并通过对账，已整批开放')}catch(e){toast(e.message,true);await refresh()}});
  bind('#drill-retry','click',async()=>{try{await drillsApi.retry(drillStore.jobId);await refresh();toast('已沿封存版本恢复，未新增副本')}catch(e){toast(e.message,true);await refresh()}});
  bind('#drill-load-research','click',async()=>{
    try{
      drillStore.research=await drillsApi.research(drillStore.jobId,200);
      const el=document.getElementById('drill-research');
      el.innerHTML='<p class="fine">共 '+drillStore.research.total+' 条，展示 '+drillStore.research.returned+' 条</p>'
        +table(drillStore.research.ratings,[{key:'anon_id',label:'匿名号'},{key:'exhibit',label:'展品'},{key:'rating',label:'星级'}],{limit:200});
    }catch(e){toast(e.message,true)}
  });
  if(drillStore.detail?.state==='open')loadOverlap();
}
async function loadOverlap(){
  try{
    drillStore.overlap=await drillsApi.overlap(drillStore.jobId);
    const el=document.getElementById('drill-overlap');if(!el)return;
    const o=drillStore.overlap;
    el.innerHTML='<div class="method-note"><b>重合数 '+o.overlap+' / 总数 '+o.total+'，理论最小值 '+o.minimum+'</b><p class="fine">reused 为真即该条复用了原配对（映射回原人后与原册同一人-展品对）。</p></div>'
      +table(o.rows.map(r=>({anon_id:r.anon_id,mapped_original:r.mapped_original,exhibit:r.exhibit,rating:r.rating,reused:r.reused?'是':'否'})),
        [{key:'anon_id',label:'副本匿名号'},{key:'mapped_original',label:'对应原编号'},{key:'exhibit',label:'展品'},{key:'rating',label:'星级'},{key:'reused',label:'复用原配对'}],{limit:30});
  }catch(e){toast(e.message,true)}
}
