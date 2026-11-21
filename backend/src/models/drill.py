from sqlalchemy import Column,Integer,String,Text,JSON,UniqueConstraint
from ..config.database import Base
class DrillJob(Base):
    """迁展演练：一次"封存原册→换号副本→对账→开放"的全过程。"""
    __tablename__='drill_jobs'
    id=Column(Integer,primary_key=True)
    # 幂等键：同一次演练重试复用同一条记录，不新增副本
    idempotency_key=Column(String(120),unique=True,nullable=False)
    name=Column(String(160),nullable=False)
    state=Column(String(20),default='sealed',nullable=False)  # sealed/building/failed/open
    # 封存快照：受理时刻的原册只读副本，含校验和；补录仍写活册，不进快照
    snapshot=Column(JSON,nullable=False)
    snapshot_sha256=Column(String(64),nullable=False)
    # 换号方案、最优性证书、对账结论
    result=Column(JSON,nullable=True)
    reconciliation=Column(JSON,nullable=True)
    # 可恢复执行的阶段标记：sealed -> permutation -> matching -> copy -> reconciled
    stage=Column(String(30),default='sealed',nullable=False)
    attempts=Column(Integer,default=0,nullable=False)
    error=Column(Text,default='')
    published_at=Column(String(40),default='')
    created_at=Column(String(40),nullable=False)
    updated_at=Column(String(40),nullable=False)
class DrillRating(Base):
    """演练评分副本：只存换号后的匿名身份；(副本编号, 展品) 唯一，同人同展品限一条。"""
    __tablename__='drill_ratings'
    __table_args__=(UniqueConstraint('job_id','anon_id','exhibit',name='uq_drill_one_pair'),)
    id=Column(Integer,primary_key=True)
    job_id=Column(Integer,nullable=False)
    anon_id=Column(String(120),nullable=False)
    exhibit=Column(String(120),nullable=False)
    rating=Column(Integer,nullable=False)
    reused=Column(Integer,default=0,nullable=False)  # 1 表示该条复用了原配对（最优重合数的逐行证据）
