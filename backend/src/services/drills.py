import os,hashlib,json
from fastapi import HTTPException
from sqlalchemy import select,func,delete
from sqlalchemy.exc import IntegrityError
from ..models.record import Record
from ..models.drill import DrillJob,DrillRating
from ..utils.serialization import row,now
from .audit import log
from . import drill_core

# 故障注入点：DRILL_FAULT=stage 时，首次执行到该阶段即抛错，用于演练中断恢复
def _fault(stage):
    if os.getenv('DRILL_FAULT')==stage:
        raise RuntimeError('故障注入：写入中断于阶段 %s'%stage)

def _canonical(rows):
    return json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':'))

def _snapshot(db):
    """受理时封存原册：只读取此刻已提交的评分，形成不可变快照与校验和。"""
    records=db.scalars(select(Record).order_by(Record.id)).all()
    rows=[]
    seen=set()
    for r in records:
        v=r.values
        item={'visitor':v['visitor'],'exhibit':v['exhibit'],'rating':int(v['rating'])}
        key=(item['visitor'],item['exhibit'])
        if key in seen:
            raise HTTPException(422,'原册存在同人同展品重复评分，拒绝受理：%s/%s'%key)
        seen.add(key);rows.append(item)
    if not rows:
        raise HTTPException(422,'原册暂无评分，无法封存演练副本')
    payload=_canonical(rows)
    return rows,hashlib.sha256(payload.encode('utf-8')).hexdigest()

def create_job(db,user,data):
    # 幂等：同一 idempotency_key 的重试返回既有演练，不新增副本
    existing=db.scalar(select(DrillJob).where(DrillJob.idempotency_key==data.idempotency_key))
    if existing:
        return row(existing),False
    rows,sha=_snapshot(db)
    job=DrillJob(
        idempotency_key=data.idempotency_key,name=data.name,
        state='sealed',stage='sealed',attempts=0,
        snapshot={'rows':rows},snapshot_sha256=sha,
        created_at=now(),updated_at=now(),
    )
    db.add(job)
    try:
        db.flush()
        log(db,user,'drill.sealed',job.id,'封存 %d 条原册评分 sha256=%s'%(len(rows),sha[:16]))
        db.commit()
    except IntegrityError:
        # 并发同受理号：回退到已落库的同一演练，保证同次重试不新增副本
        db.rollback()
        rival=db.scalar(select(DrillJob).where(DrillJob.idempotency_key==data.idempotency_key))
        if rival:return row(rival),False
        raise
    return row(job),True

def _run_build(db,job):
    """沿封存快照执行（或恢复）换号副本构造。同 job 同 seed，结果确定性，可安全重跑。"""
    rows=job.snapshot['rows']
    # 校验封存版本未被篡改
    if hashlib.sha256(_canonical(rows).encode('utf-8')).hexdigest()!=job.snapshot_sha256:
        raise HTTPException(500,'封存快照校验和不符，已中止恢复')
    job.attempts+=1;job.state='building';job.updated_at=now();db.commit()
    seed=int(hashlib.sha256(('drill|'+job.idempotency_key).encode()).hexdigest()[:12],16)
    try:
        job.stage='matching';_fault('matching');db.commit()
        result=drill_core.build_copy(rows,seed)
        job.stage='copy';_fault('copy');db.commit()
        # 重跑恢复：先清掉上一轮未完成的副本行，再整体写入，保证不新增副本
        db.execute(delete(DrillRating).where(DrillRating.job_id==job.id))
        db.add_all([DrillRating(job_id=job.id,anon_id=r['anon_id'],exhibit=r['exhibit'],
                                rating=r['rating'],reused=r['reused']) for r in result['copy_rows']])
        job.result=result;job.stage='reconciled';_fault('reconciled');db.commit()
        recon=_reconcile(db,job)
        job.reconciliation=recon
        if not recon['passed']:
            job.state='failed';job.error='对账未通过：'+ ';'.join(recon['failures'])
            job.updated_at=now();db.commit()
            raise HTTPException(422,job.error)
        job.state='open';job.published_at=now();job.error='';job.updated_at=now()
        log(db,'drill-builder','drill.opened',job.id,
            '最小复用 %d/%d，对账全部通过'%(result['metrics']['min_reused'],
                                       result['metrics']['total_ratings']))
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        job.state='failed';job.error=str(e)[:2000];job.updated_at=now();db.commit()
        raise HTTPException(500,'演练写入中断，可按同一受理号重试从封存版本恢复：'+str(e)[:200])

def retry_job(db,user,job_id):
    job=db.get(DrillJob,job_id)
    if not job:raise HTTPException(404,'未找到演练任务')
    if job.state=='open':return row(job)
    log(db,user,'drill.retry',job.id,'第 %d 次尝试，沿封存版本恢复'%(job.attempts+1))
    _run_build(db,job)
    return row(job)

def start_job(db,user,job_id):
    job=db.get(DrillJob,job_id)
    if not job:raise HTTPException(404,'未找到演练任务')
    if job.state in ('building','open'):return row(job)
    log(db,user,'drill.start',job.id,'发起换号副本构造')
    _run_build(db,job)
    return row(job)

def _reconcile(db,job):
    """对账：副本逐条对照封存原册与约束，全部通过才允许开放。"""
    rows=job.snapshot['rows'];result=job.result
    copy=db.scalars(select(DrillRating).where(DrillRating.job_id==job.id)).all()
    failures=[];checks=[]
    def add(name,ok,detail):
        checks.append({'item':name,'passed':bool(ok),'detail':detail})
        if not ok:failures.append(name+'：'+detail)
    # 1 总条数
    add('总评分条数',len(copy)==len(rows),
        '原册 %d / 副本 %d'%(len(rows),len(copy)))
    # 2 每人评分条数（副本匿名号映射回原人）
    inv={x['anon']:x['original'] for x in result['permutation']}
    exp_deg={}
    for r in rows:exp_deg[r['visitor']]=exp_deg.get(r['visitor'],0)+1
    got_deg={}
    for r in copy:
        op=inv.get(r.anon_id)
        got_deg[op]=got_deg.get(op,0)+1
    add('每人评分条数',got_deg==exp_deg,'按置换映射回原人后逐人一致')
    # 3 每展品各星级人数
    def hist(data):
        h={}
        for r in data:
            e=r['exhibit'] if isinstance(r,dict) else r.exhibit
            star=int(r['rating'] if isinstance(r,dict) else r.rating)
            h[(e,star)]=h.get((e,star),0)+1
        return h
    add('每展品各星级人数',hist(rows)==hist(copy),'展品×星级直方图完全一致')
    # 4 同人同展品限一条
    keys=[(r.anon_id,r.exhibit) for r in copy]
    add('同人同展品唯一',len(keys)==len(set(keys)),'副本 %d 条无重复配对'%len(keys))
    # 5 匿名号确为原编号的置换
    anon_set={r.anon_id for r in copy};orig_set={r['visitor'] for r in rows}
    add('匿名号为置换',set(inv.keys())==orig_set and anon_set<=orig_set and len(inv)==len(orig_set),
        '%d 个编号一一对应，无新增无丢失'%len(orig_set))
    # 6 最小复用：副本逐行重合数 == 证书最优值，且与独立最大流/最小割吻合
    orig_pairs={(r['visitor'],r['exhibit']) for r in rows}
    overlap=sum(1 for r in copy if (inv[r.anon_id],r.exhibit) in orig_pairs)
    cert=result['certificate']
    add('原配对复用为全局最小',
        overlap==cert['min_reused']==cert['total_ratings']-cert['zero_edge_max_flow']
        and cert['min_cut_capacity']==cert['dinic_independent_max_flow']==cert['zero_edge_max_flow'],
        '逐行重合 %d，最小费用流与 Dinic 最大流/最小割均为 %d，下界可达'
        %(overlap,cert['min_reused']))
    # 7 封存快照校验和
    sha_ok=hashlib.sha256(_canonical(rows).encode()).hexdigest()==job.snapshot_sha256
    add('封存快照完整性',sha_ok,'sha256='+job.snapshot_sha256[:16]+'…')
    return {'passed':not failures,'checks':checks,'failures':failures,
            'overlap':overlap,'checked_at':now()}

def list_jobs(db):
    out=[]
    for j in db.scalars(select(DrillJob).order_by(DrillJob.id.desc())):
        d=row(j)
        d.pop('snapshot',None)
        if j.result:d['metrics']=j.result['metrics']
        out.append(d)
    return out

def get_job(db,job_id):
    job=db.get(DrillJob,job_id)
    if not job:raise HTTPException(404,'未找到演练任务')
    return job

def overlap(db,job_id):
    """页面核对重合数：返回逐行配对与复用统计，可人工复核。"""
    job=get_job(db,job_id)
    if job.state!='open':raise HTTPException(409,'演练尚未通过对账开放，暂不可核对')
    inv={x['anon']:x['original'] for x in job.result['permutation']}
    orig={(r['visitor'],r['exhibit']) for r in job.snapshot['rows']}
    copy=db.scalars(select(DrillRating).where(DrillRating.job_id==job.id).order_by(DrillRating.id)).all()
    rows=[{'anon_id':r.anon_id,'mapped_original':inv[r.anon_id],'exhibit':r.exhibit,
           'rating':r.rating,'reused':bool(r.reused),
           'is_original_pair':(inv[r.anon_id],r.exhibit) in orig} for r in copy]
    reused=sum(1 for r in rows if r['reused'])
    return {'job_id':job.id,'state':job.state,'total':len(rows),
            'overlap':reused,'minimum':job.result['certificate']['min_reused'],
            'certificate':job.result['certificate'],
            'reconciliation':job.reconciliation,'rows':rows}

def research_copy(db,job_id,limit=200):
    """对账通过后整批开放给研究选用：只暴露换号后的匿名评分，不回显原编号。"""
    job=get_job(db,job_id)
    if job.state!='open':raise HTTPException(409,'副本未开放：当前状态 %s'%job.state)
    q=select(DrillRating).where(DrillRating.job_id==job.id).order_by(DrillRating.id)
    total=db.scalar(select(func.count()).select_from(DrillRating).where(DrillRating.job_id==job.id))
    items=[{'anon_id':r.anon_id,'exhibit':r.exhibit,'rating':r.rating}
           for r in db.scalars(q.limit(limit))]
    return {'job_id':job.id,'published_at':job.published_at,'total':total,
            'returned':len(items),'ratings':items}
