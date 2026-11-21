"""迁展演练：换号副本构造与"最少原配对复用"的多项式时间求解。

问题形式化
----------
原册是一张二分图 G=(P,E,R)：左侧 P 为原匿名编号（人），右侧 E 为展品，
每条评分是一条边 (p,e)，边上带星级 r∈{1..5}。每人评分条数即其度数 d(p)，
每件展品各星级人数即该展品邻边上的星级直方图 h(e,r)。

换号：取一个 P 上的随机置换 π，新人编号 anon=π(p)。要求副本满足
  (1) 每个新人 anon 的评分条数仍为 d(π^{-1}(anon))（保留每人的评分条数）；
  (2) 每件展品的评分总数、各星级人数仍为 h(e,·)（保留每展品各星级人数）；
  (3) 同人同展品至多一条（二分简单图）。

"原配对复用"：副本中 (anon,e) 与原册中 (p,e) 是同一个人-展品对，即
新边 (p',e) 恰好是原边。目标是让这样的重合边数最少。

建模（不穷举，多项式时间）
--------------------------
保留每个人的度数，等价于在同一组人、同一组展品之间重新安排一个满足
度数上下限的简单二分图。令 Z 为"非原边"子图（容量 1 的边 (p,e) 当且仅当
原册中不存在该边）。在 Z 上能安排的边越多，需要复用的原边就越少：
    最小复用数 = 总评分条数 N − （Z 上的最大可行流 M）。
Z 上的流是"带度数上下限的二分 b-匹配"，用源/汇容量边刻画：
    s → p 容量 d(p)；p → e（仅非原边）容量 1；e → t 容量 deg(e)。
该最大流可由最小费用流（原边费用 1、非原边费用 0）一次算出，
也可由独立的 Dinic 最大流在 Z 上直接算出 M，并据最大流-最小割定理
给出最小割容量作为最优性的可核查下界证明。二百人规模为多项式时间、秒级完成，
不穷举任何置换或配对方案。
"""
import random
from collections import deque

STARS=(1,2,3,4,5)

# ---------------------------------------------------------------------------
# 最小费用最大流（SPFA 逐最短路增广），费用 0/1：原边=1，非原边=0
# ---------------------------------------------------------------------------
class MinCostFlow:
    def __init__(self,n):
        self.n=n
        self.g=[[] for _ in range(n)]
    def add_edge(self,u,v,cap,cost):
        self.g[u].append([v,cap,cost,len(self.g[v])])
        self.g[v].append([u,0,-cost,len(self.g[u])-1])
    def solve(self,s,t):
        n=self.n;flow=cost=0
        INF=float('inf')
        while True:
            dist=[INF]*n;pv=[-1]*n;pe=[-1]*n;inq=[False]*n
            dist[s]=0;q=deque([s]);inq[s]=True
            while q:
                u=q.popleft();inq[u]=False
                for i,(v,cap,c,_) in enumerate(self.g[u]):
                    if cap>0 and dist[u]+c<dist[v]:
                        dist[v]=dist[u]+c;pv[v]=u;pe[v]=i
                        if not inq[v]:q.append(v);inq[v]=True
            if pv[t]<0:break
            add=INF;v=t
            while v!=s:
                add=min(add,self.g[pv[v]][pe[v]][1]);v=pv[v]
            v=t
            while v!=s:
                e=self.g[pv[v]][pe[v]];e[1]-=add
                self.g[v][e[3]][1]+=add;v=pv[v]
            flow+=add;cost+=add*dist[t]
        return flow,cost
    def edge_flow(self,u,slot):
        """返回 u 的第 slot 条出边当前已用流量（= 原始容量 - 剩余容量）。"""
        v,cap,cost,rev=self.g[u][slot]
        reverse=self.g[v][rev]
        return reverse[1]

# ---------------------------------------------------------------------------
# 独立校验器：Dinic 最大流，只在"非原边"子图 Z 上运行
# ---------------------------------------------------------------------------
class _Dinic:
    def __init__(self,n):
        self.n=n;self.g=[[] for _ in range(n)]
    def add_edge(self,u,v,cap):
        self.g[u].append([v,cap,len(self.g[v])])
        self.g[v].append([u,0,len(self.g[u])-1])
    def bfs(self,s,t,level):
        for i in range(self.n):level[i]=-1
        level[s]=0;q=deque([s])
        while q:
            u=q.popleft()
            for v,cap,_ in self.g[u]:
                if cap>0 and level[v]<0:
                    level[v]=level[u]+1;q.append(v)
        return level[t]>=0
    def dfs(self,u,t,f,it,level):
        if u==t:return f
        while it[u]<len(self.g[u]):
            idx=it[u];v,cap,rev=self.g[u][idx]
            if cap>0 and level[v]==level[u]+1:
                got=self.dfs(v,t,min(f,cap),it,level)
                if got:
                    self.g[u][idx][1]-=got
                    self.g[v][rev][1]+=got
                    return got
            it[u]+=1
        return 0
    def max_flow(self,s,t):
        flow=0;level=[-1]*self.n;INF=float('inf')
        while self.bfs(s,t,level):
            it=[0]*self.n
            while True:
                f=self.dfs(s,t,INF,it,level)
                if not f:break
                flow+=f
        return flow
    def reachable_from(self,s):
        """最大流后残量网络可达集合，用于最小割证书。"""
        seen={s};q=deque([s])
        while q:
            u=q.popleft()
            for v,cap,_ in self.g[u]:
                if cap>0 and v not in seen:
                    seen.add(v);q.append(v)
        return seen

def _index(members):
    return {m:i for i,m in enumerate(members)}

def build_copy(rows,seed):
    """依据原册评分行构造最优换号副本。

    rows: [{'visitor','exhibit','rating'}]，已通过同人同展品唯一性校验。
    返回 dict：置换、副本行（含 reused 逐行标记）、最优性证书、统计与计数。
    """
    if not rows:
        raise ValueError('原册为空，无法生成演练副本')
    persons=sorted({r['visitor'] for r in rows})
    exhibits=sorted({r['exhibit'] for r in rows})
    pi={p:i for i,p in enumerate(persons)}
    ei=_index(exhibits)
    nP=len(persons);nE=len(exhibits)

    # 原边集合与查找表
    original=set()
    rating_lookup={}
    for r in rows:
        key=(pi[r['visitor']],ei[r['exhibit']])
        if key in original:
            raise ValueError('原册存在同人同展品重复评分：%s / %s'%(r['visitor'],r['exhibit']))
        original.add(key)
        rating_lookup[key]=int(r['rating'])

    deg_p=[0]*nP
    deg_e=[0]*nE
    star_hist={(j,s):0 for j in range(nE) for s in STARS}
    for (i,j),star in rating_lookup.items():
        deg_p[i]+=1;deg_e[j]+=1;star_hist[(j,star)]+=1
    total=len(original)

    rng=random.Random(seed)
    perm=persons.copy();rng.shuffle(perm)
    # anon_of[原人] = 新人编号；inverse[新人编号] = 原人
    anon_of={p:perm[i] for i,p in enumerate(persons)}
    inverse={anon:p for p,anon in anon_of.items()}

    # 网络节点：s=0，人员 1..nP，展品 1+nP..nP+nE，t
    s=0;t=1+nP+nE;V=t+1
    # 完整网络：s→p 容量=人数；p→e 容量1（非原边费用0、原边费用1）；e→t 容量=展品数。
    # 一次最小费用最大流同时得到：总流 N，以及其中费用1（复用原边）的最小条数。
    # Z 上的最大流 M（全0费用能安排的上限）由独立 Dinic 给出，避免在残量网上二次求解。
    mcf=MinCostFlow(V)
    pair_slot={}
    for i in range(nP):
        mcf.add_edge(s,1+i,deg_p[i],0)
    for i in range(nP):
        for j in range(nE):
            is_original=(i,j) in original
            pair_slot[(i,j)]=len(mcf.g[1+i])
            mcf.add_edge(1+i,1+nP+j,1,1 if is_original else 0)
    for j in range(nE):
        mcf.add_edge(1+nP+j,t,deg_e[j],0)
    full_flow,min_cost=mcf.solve(s,t)
    if full_flow!=total:
        raise RuntimeError('网络无法满足全部度数约束，输入结构异常')

    # 读取最终人员-展品安排
    chosen=[[] for _ in range(nP)]
    for (i,j),slot in pair_slot.items():
        if mcf.edge_flow(1+i,slot)==1:
            chosen[i].append(j)

    # 独立 Dinic 校验：在同一 Z 上重算最大流 M，并取最小割可达集
    dinic=_Dinic(V)
    for i in range(nP):
        dinic.add_edge(s,1+i,deg_p[i])
    for i in range(nP):
        for j in range(nE):
            if (i,j) not in original:
                dinic.add_edge(1+i,1+nP+j,1)
    for j in range(nE):
        dinic.add_edge(1+nP+j,t,deg_e[j])
    dinic_max=dinic.max_flow(s,t)
    reachable=dinic.reachable_from(s)
    # 由最小割容量独立汇总（割=S到T的饱和容量边之和），应等于 dinic_max
    cut_edges=[];cut_capacity=0
    for i in range(nP):
        if (1+i) not in reachable:  # 源边 s->p 跨越割
            cut_edges.append({'kind':'source','node':persons[i],'capacity':deg_p[i]})
            cut_capacity+=deg_p[i]
    for i in range(nP):
        if (1+i) in reachable:
            for j in range(nE):
                if (i,j) not in original and (1+nP+j) not in reachable:
                    cut_edges.append({'kind':'pair','person':persons[i],
                                      'exhibit':exhibits[j],'capacity':1})
                    cut_capacity+=1
    for j in range(nE):
        if (1+nP+j) in reachable:  # 汇边 e->t 跨越割
            cut_edges.append({'kind':'sink','node':exhibits[j],'capacity':deg_e[j]})
            cut_capacity+=deg_e[j]

    zero_flow=dinic_max  # Z 上的最大非原边安排，独立于最小费用流求得
    if cut_capacity!=dinic_max or min_cost!=total-zero_flow:
        raise RuntimeError('两套求解器结果不一致，最优性校验失败')

    # 星级重排：保持每展品各星级人数；在该展品被安排到的人之间按固定顺序发牌
    # 原 (人,展品) 的星级仅用于取数，最终星级由展品直方图决定
    exhibit_persons={j:[] for j in range(nE)}
    for i,js in enumerate(chosen):
        for j in js:
            exhibit_persons[j].append(i)
    assigned={}  # (i,j)->star
    for j in range(nE):
        pool=[]
        for star in STARS:
            pool.extend([star]*star_hist[(j,star)])
        members=sorted(exhibit_persons[j])
        if len(pool)!=len(members):
            raise RuntimeError('展品 %s 的星级名额与安排人数不一致'%exhibits[j])
        # 确定性发牌：人按原编号排序，星级池按 1..5 顺序，避免依赖随机遍历
        for i,star in zip(members,pool):
            assigned[(i,j)]=star

    copy_rows=[]
    reused_count=0
    for i in range(nP):
        for j in sorted(chosen[i]):
            reused=1 if (i,j) in original else 0
            reused_count+=reused
            copy_rows.append({
                'anon_id':anon_of[persons[i]],
                'exhibit':exhibits[j],
                'rating':assigned[(i,j)],
                'reused':reused,
            })
    if reused_count!=min_cost:
        raise RuntimeError('逐行复用计数与最小费用不符')

    # 副本侧统计，供对账
    copy_deg={}
    copy_hist={(e,s):0 for e in exhibits for s in STARS}
    for r in copy_rows:
        copy_deg[r['anon_id']]=copy_deg.get(r['anon_id'],0)+1
        copy_hist[(r['exhibit'],r['rating'])]+=1
    person_degree={anon_of[p]:deg_p[pi[p]] for p in persons}

    certificate={
        'model':'二分图 b-匹配 / 最小费用最大流（原边费用1、非原边费用0）',
        'total_ratings':total,
        'zero_edge_max_flow':zero_flow,
        'min_cost_flow':full_flow,
        'min_reused':min_cost,
        'formula':'min_reused = total_ratings − zero_edge_max_flow = %d − %d = %d'
                  %(total,zero_flow,min_cost),
        'dinic_independent_max_flow':dinic_max,
        'min_cut_capacity':cut_capacity,
        'min_cut_theorem':'最大流-最小割定理：Z 上最大流 M=%d 等于最小割容量 %d，'
                          '故任何方案至多安排 %d 条非原边，至少复用 %d 条原边；'
                          '本方案恰好达到该下界，为全局最优。'
                          %(dinic_max,cut_capacity,dinic_max,total-dinic_max),
        'min_cut_edges':cut_edges,
        'complexity':'节点 O(P+E)、边 O(PE)；SPFA 最小费用流与 Dinic 均为多项式时间，'
                     '二百人规模不穷举任何置换或配对方案',
        'seed':seed,
    }
    return {
        'persons':persons,
        'exhibits':exhibits,
        'permutation':[{'original':p,'anon':anon_of[p]} for p in persons],
        'copy_rows':copy_rows,
        'certificate':certificate,
        'person_degree':person_degree,
        'original_star_hist':{('%s|%d'%(e,s)):star_hist[(ei[e],s)]
                              for e in exhibits for s in STARS},
        'copy_star_hist':{('%s|%d'%(e,s)):copy_hist[(e,s)]
                          for e in exhibits for s in STARS},
        'metrics':{
            'person_count':nP,'exhibit_count':nE,'total_ratings':total,
            'min_reused':min_cost,'reuse_rate':round(min_cost/total,6),
        },
    }
