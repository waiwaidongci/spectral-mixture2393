from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from ..config.database import get_db
from ..controllers.dependencies import current_user,roles
from ..constants.roles import Role
from ..schemas.calibration import CalibrationInput,CalibrationRederive,CalibrationOutput
from ..services.calibration_service import list_calibrations,create_calibration,rederive_calibration
router=APIRouter(prefix="/calibrations",tags=["calibrations"])
@router.get("",response_model=list[CalibrationOutput])
def index(library_id:int|None=None,db:Session=Depends(get_db),user=Depends(current_user)):return list_calibrations(db,library_id)
@router.post("",status_code=201,response_model=CalibrationOutput)
def create(data:CalibrationInput,db:Session=Depends(get_db),user=Depends(roles(Role.ADMIN,Role.ANALYST))):
    try:return create_calibration(db,data,user)
    except ValueError as e:raise HTTPException(422,str(e))
@router.post("/{cid}/rederive",status_code=201,response_model=CalibrationOutput)
def rederive(cid:int,data:CalibrationRederive,db:Session=Depends(get_db),user=Depends(roles(Role.ADMIN,Role.ANALYST))):
    try:return rederive_calibration(db,cid,data,user)
    except ValueError as e:raise HTTPException(422 if "不存在" not in str(e) else 404,str(e))
