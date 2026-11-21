from fastapi import APIRouter,Depends
from ..config.database import db_session
from ..schemas.drill import DrillInput
from ..services.auth import current_user,writer
from ..controllers.drills import DrillsController as C
router=APIRouter()
@router.get('/drills')
def drills(db=Depends(db_session),u=Depends(current_user)):return C.list(db)
@router.post('/drills')
def create(data:DrillInput,db=Depends(db_session),u=Depends(writer)):
    job,created=C.create(db,u,data)
    return {'created':created,'job':job}
@router.get('/drills/{id}')
def detail(id:int,db=Depends(db_session),u=Depends(current_user)):return C.get(db,id)
@router.post('/drills/{id}/start')
def start(id:int,db=Depends(db_session),u=Depends(writer)):return C.start(db,u,id)
@router.post('/drills/{id}/retry')
def retry(id:int,db=Depends(db_session),u=Depends(writer)):return C.retry(db,u,id)
@router.get('/drills/{id}/overlap')
def overlap(id:int,db=Depends(db_session),u=Depends(current_user)):return C.overlap(db,id)
@router.get('/drills/{id}/research-copy')
def research(id:int,limit:int=200,db=Depends(db_session),u=Depends(current_user)):
    return C.research(db,id,min(max(limit,1),1000))
