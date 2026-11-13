import numpy as np
from ..models import SpectralLibrary,BlankCalibration
from .audit_service import log
from .calibration_algorithm import (CALIBRATION_RULE_VERSION,MAX_BLANK_REPLICATES,
    source_fingerprint,calibration_fingerprint,estimate_payload,evaluate_blank_calibration)

def library_wavelengths(library):
    wavelengths=np.asarray(library.wavelengths,dtype=float)
    if wavelengths.ndim!=1 or not np.isfinite(wavelengths).all() or np.any(np.diff(wavelengths)<=0):
        raise ValueError("光谱库波长必须有限且严格递增")
    return wavelengths

def library_band_count(library):
    return len(library_wavelengths(library))

def calibration_summary(row):
    return {"id":row.id,"library_id":row.library_id,"name":row.name,"source":row.source,"band_count":row.band_count,
        "rule_version":row.rule_version,"rule_current":row.rule_version==CALIBRATION_RULE_VERSION,
        "source_hash":row.source_hash,"calibration_hash":row.calibration_hash,"readings_count":len(row.readings or []),
        "effective_measurements":row.effective_measurements,"degrees_of_freedom":row.degrees_of_freedom,
        "noise_rms":row.noise_rms,"condition_number":row.condition_number,"derived_from_id":row.derived_from_id,
        "owner":row.owner,"created_at":row.created_at,"readings":row.readings,"estimate":row.estimate}

def list_calibrations(db,library_id=None):
    query=db.query(BlankCalibration).order_by(BlankCalibration.id.desc())
    if library_id is not None:query=query.filter_by(library_id=library_id)
    return [calibration_summary(row) for row in query]

def get_calibration(db,calibration_id):
    row=db.get(BlankCalibration,calibration_id)
    if not row:raise ValueError("空白校准不存在")
    return row

def library_calibration(db,calibration_id,library):
    row=get_calibration(db,calibration_id)
    if row.library_id!=library.id:raise ValueError("空白校准不属于所选光谱库")
    if row.band_count!=library_band_count(library):raise ValueError("空白校准的波段数与所选光谱库不一致")
    if row.rule_version!=CALIBRATION_RULE_VERSION:
        raise ValueError(f"该校准按旧规则{row.rule_version}估计；新研究须先按当前规则{CALIBRATION_RULE_VERSION}从同一空白读数重算")
    return row

def frozen_calibration(row):
    """Immutable calibration source copied into a run snapshot."""
    return {"id":row.id,"name":row.name,"rule_version":row.rule_version,"source_hash":row.source_hash,
        "calibration_hash":row.calibration_hash,"readings_count":len(row.readings or []),
        "effective_measurements":row.effective_measurements,"degrees_of_freedom":row.degrees_of_freedom,
        "band_count":row.band_count,"noise_rms":row.noise_rms,"condition_number":row.condition_number,
        "readings":row.readings,"estimate":row.estimate}

def _store(db,library,readings,name,source,user,derived_from=None):
    wavelengths=library_wavelengths(library);band_count=len(wavelengths)
    if not isinstance(readings,list) or not readings:raise ValueError("空白测谱至少需要一次重复读数")
    if len(readings)>MAX_BLANK_REPLICATES:raise ValueError(f"空白重复最多{MAX_BLANK_REPLICATES}次，请拆分批次或减少行数")
    evaluation=evaluate_blank_calibration(readings,band_count,wavelengths)
    if not evaluation["valid"]:raise ValueError(evaluation["reason"])
    estimate=estimate_payload(band_count,evaluation["effective_measurements"],evaluation["degrees_of_freedom"],
        evaluation["mean"],evaluation["covariance"],evaluation["condition_number"],evaluation["noise_rms"])
    source_hash=source_fingerprint(wavelengths,evaluation["normalized_readings"])
    calibration_hash=calibration_fingerprint(source_hash,CALIBRATION_RULE_VERSION,estimate)
    existing=db.query(BlankCalibration).filter_by(calibration_hash=calibration_hash).first()
    if existing:
        if derived_from is None:raise ValueError(f"相同空白读数已存在为校准 #{existing.id}（{existing.name}），未重复建立")
        raise ValueError(f"按当前规则重算得到的校准与 #{existing.id} 相同，无需重建")
    if db.query(BlankCalibration).filter_by(library_id=library.id,name=name).first():
        raise ValueError("同一光谱库内空白校准名称须唯一")
    row=BlankCalibration(library_id=library.id,name=name,source=source,readings=evaluation["normalized_readings"],
        band_count=band_count,rule_version=CALIBRATION_RULE_VERSION,source_hash=source_hash,
        calibration_hash=calibration_hash,estimate=estimate,effective_measurements=evaluation["effective_measurements"],
        degrees_of_freedom=evaluation["degrees_of_freedom"],noise_rms=evaluation["noise_rms"],
        condition_number=evaluation["condition_number"],derived_from_id=derived_from.id if derived_from else None,
        owner=user.name)
    db.add(row);db.flush()
    log(db,user.email,"calibration.rederive" if derived_from else "calibration.create",calibration_hash)
    db.commit()
    return calibration_summary(row)

def create_calibration(db,data,user):
    library=db.get(SpectralLibrary,data.library_id)
    if not library:raise ValueError("光谱库不存在")
    return _store(db,library,data.readings,data.name,data.source,user)

def rederive_calibration(db,calibration_id,data,user):
    row=get_calibration(db,calibration_id)
    library=db.get(SpectralLibrary,row.library_id)
    if not library:raise ValueError("校准所属光谱库不存在")
    if row.rule_version==CALIBRATION_RULE_VERSION and data.name==row.name:
        raise ValueError("该校准已使用当前规则，无需重算；如需同值归档请改用其他名称")
    return _store(db,library,row.readings,data.name,row.source,user,derived_from=row)
