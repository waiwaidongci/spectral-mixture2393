import numpy as np
from .unmix_algorithm import matrix_diagnostics
from .noise_algorithm import conditional_refits
from .calibration_algorithm import validate_frozen_calibration
from ..utils.fingerprint import fingerprint

LEGACY_ALGORITHM_VERSION="simplex-nullspace-kkt-gaussian-v2"
JOINT_ALGORITHM_VERSION="simplex-nullspace-kkt-blank-joint-gls-v1"
LEGACY_ASSUMPTIONS="固定校准端元的线性混合；权重非负且和为1。噪声在各波段独立同方差Gaussian，sigma由用户给定；高残差只提示失配，不是噪声或成分真实性检验。"
JOINT_ASSUMPTIONS="固定校准端元的线性混合；权重非负且和为1。噪声按空白测谱估计的跨波段联合协方差生成，并以广义最小二乘重拟合；高残差仍只提示失配，不是噪声或成分真实性检验。"

def analyze_unmix(snapshot,noise_sigma=.005,repeats=80,seed=2026,calibration=None):
    library=snapshot['library'];members=sorted(snapshot['endmembers'],key=lambda e:e['code']);samples=sorted(snapshot['samples'],key=lambda s:s['code'])
    if not 1<=len(samples)<=6 or len(samples)*repeats>480:raise ValueError("选择1–6个样本，样本数×重复数不得超过480")
    if len({s['code'] for s in samples})!=len(samples):raise ValueError("混合样本编号重复")
    if type(seed) is not int or not 0<=seed<=2147483647:raise ValueError("根种子须为0–2147483647整数")
    wavelengths=np.asarray(library['wavelengths'],dtype=float)
    if wavelengths.ndim!=1 or not np.isfinite(wavelengths).all() or np.any(np.diff(wavelengths)<=0):raise ValueError("波长须有限且严格递增")
    A=np.array([e['spectrum'] for e in members],dtype=float).T
    _,diagnostics=matrix_diagnostics(A)
    if len(wavelengths)!=A.shape[0]:raise ValueError("波长与端元波段数不匹配")
    if not diagnostics['supported']:raise ValueError(diagnostics['reason'])
    if calibration is None:
        algorithm_version=LEGACY_ALGORITHM_VERSION;assumptions=LEGACY_ASSUMPTIONS;decoded_calibration=None
    else:
        decoded_calibration=validate_frozen_calibration(calibration,wavelengths)
        if len(calibration.get('readings',[]))!=decoded_calibration['readings_count']:raise ValueError("冻结空白校准的读数计数与来源不一致")
        algorithm_version=JOINT_ALGORITHM_VERSION;assumptions=JOINT_ASSUMPTIONS
    streams=np.random.SeedSequence(seed).spawn(len(samples));results=[]
    for sample,child in zip(samples,streams):
        refits=conditional_refits(A,sample['observed'],noise_sigma,repeats,child,calibration=decoded_calibration)
        high_threshold=max(3*noise_sigma,1e-8) if calibration is None else max(3*decoded_calibration['noise_rms'],1e-8)
        results.append({"sample_id":sample['id'],"code":sample['code'],"name":sample['name'],"observed":sample['observed'],"spawn_key":list(child.spawn_key),"high_residual":refits['point_fit']['rmse']>high_threshold,**refits})
    canonical={"library":library,"endmembers":members,"samples":samples}
    fingerprint_payload={"method":algorithm_version,"snapshot":canonical,"noise_sigma":noise_sigma if calibration is None else None,"repeats":repeats,"seed":seed}
    if calibration is not None:fingerprint_payload["calibration"]={"rule_version":decoded_calibration['rule_version'],"source_hash":decoded_calibration['source_hash'],"calibration_hash":decoded_calibration['calibration_hash']}
    input_hash=fingerprint(fingerprint_payload)
    return {"algorithm_version":algorithm_version,"library":library,"endmembers":members,"samples":results,"diagnostics":diagnostics,"noise_sigma":noise_sigma if calibration is None else None,"repeats":repeats,"seed":seed,"calibration":calibration_result(calibration,decoded_calibration),"input_snapshot":canonical,"input_hash":input_hash,"assumptions":assumptions,"quantile_note":"分位范围是条件扰动情景，不是配比真值的覆盖保证。","feasibility_tolerance":1e-10,"condition_limit":1e6}


def calibration_result(frozen,decoded):
    """Small JSON-safe provenance block; the full frozen source stays in input_snapshot."""
    if decoded is None:return None
    return {"id":frozen.get('id'),"name":frozen.get('name'),"rule_version":decoded['rule_version'],
        "source_hash":decoded['source_hash'],"calibration_hash":decoded['calibration_hash'],
        "readings_count":decoded['readings_count'],"effective_measurements":decoded['effective_measurements'],
        "degrees_of_freedom":decoded['degrees_of_freedom'],"band_count":decoded['band_count'],
        "noise_rms":decoded['noise_rms'],"condition_number":decoded['condition_number']}
