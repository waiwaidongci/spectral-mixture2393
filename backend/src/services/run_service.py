import csv,io
import numpy as np
from redis import Redis
from fastapi import HTTPException
from ..models import SpectralLibrary,Endmember,MixtureSample,UnmixRun,ReplicationNote
from ..config.settings import REDIS_URL
from ..utils.serialize import record
from .unmix_algorithm import matrix_diagnostics
from .calibration_service import library_calibration,frozen_calibration
from .audit_service import log
queue=Redis.from_url(REDIS_URL,decode_responses=True)
def list_runs(db):return [record(r) for r in db.query(UnmixRun).order_by(UnmixRun.id.desc())]
def get_run(db,rid):
    row=db.get(UnmixRun,rid)
    if not row:raise HTTPException(404,"解混运行不存在")
    return row

def create_snapshot(db,library,sample_ids,calibration=None):
    members=db.query(Endmember).filter_by(library_id=library.id).order_by(Endmember.code).all()
    samples=db.query(MixtureSample).filter(MixtureSample.id.in_(sample_ids),MixtureSample.library_id==library.id).order_by(MixtureSample.code).all()
    if len(samples)!=len(sample_ids):raise HTTPException(422,"样本重复、不存在或不属于所选光谱库")
    snapshot={"library":record(library),"endmembers":[record(e) for e in members],"samples":[record(s) for s in samples]}
    if calibration is not None:snapshot["noise_calibration"]=frozen_calibration(calibration)
    return snapshot
def create_run(db,data,user):
    library=db.get(SpectralLibrary,data.library_id)
    if not library:raise HTTPException(404,"光谱库不存在")
    if len(set(data.sample_ids))!=len(data.sample_ids) or len(data.sample_ids)*data.repeats>480:raise HTTPException(422,"样本不可重复，样本数×重复数不得超过480")
    calibration=None
    mode=data.noise_mode or "legacy"
    if mode=="blank":
        if data.calibration_id is None:raise HTTPException(422,"选择空白联合噪声时必须指定空白校准")
        if data.noise_sigma is not None:raise HTTPException(422,"空白联合噪声不使用独立sigma；请勿同时提交sigma")
        try:calibration=library_calibration(db,data.calibration_id,library)
        except ValueError as e:
            detail=str(e)
            status=404 if "不存在" in detail else 409 if "旧规则" in detail else 422
            raise HTTPException(status,detail) from e
    elif mode=="legacy" and data.calibration_id is not None:raise HTTPException(422,"未选择空白校准时不能指定calibration_id")
    snapshot=create_snapshot(db,library,data.sample_ids,calibration)
    try:
        _,d=matrix_diagnostics(np.array([e['spectrum'] for e in snapshot['endmembers']]).T)
        if not d['supported']:raise ValueError(d['reason'])
    except ValueError as e:raise HTTPException(422,str(e)) from e
    row=UnmixRun(name=data.name,library_id=data.library_id,sample_ids=data.sample_ids,noise_sigma=None if calibration else data.noise_sigma,repeats=data.repeats,seed=data.seed,calibration_id=calibration.id if calibration else None,input_snapshot=snapshot,owner=user.name)
    db.add(row);db.flush();log(db,user.email,"unmix.enqueue",row.id);db.commit()
    try:queue.rpush("spectral:jobs",row.id)
    except Exception as e:
        row.status="failed";row.error="队列不可用，请重提";db.commit();raise HTTPException(503,row.error) from e
    return record(row)
def export_run(db,rid):
    row=get_run(db,rid)
    if row.status!="completed" or not db.query(ReplicationNote).filter_by(run_id=rid,status="approved").first():raise HTTPException(403,"仅获批完成研究可导出")
    result=row.result;calibration=result.get('calibration')
    out=io.StringIO();w=csv.writer(out)
    w.writerow(['sample','endmember','weight','conditional_q025','conditional_q975','rss','rmse','noise_model','noise_sigma','noise_calibration_id','noise_calibration_hash','effective_measurements','degrees_of_freedom','repeats','root_seed','input_hash'])
    for s in result['samples']:
        for i,e in enumerate(result['endmembers']):
            w.writerow([s['code'],e['code'],s['point_fit']['weights'][i],s['lower'][i],s['upper'][i],s['point_fit']['rss'],s['point_fit']['rmse'],
                s.get('noise_model','legacy-independent'),'' if row.noise_sigma is None else row.noise_sigma,
                '' if not calibration else calibration.get('id'),'' if not calibration else calibration.get('calibration_hash'),
                '' if not calibration else calibration.get('effective_measurements'),'' if not calibration else calibration.get('degrees_of_freedom'),
                row.repeats,row.seed,result['input_hash']])
    return out.getvalue()
