import math
import numpy as np
from .unmix_algorithm import fit_simplex

def _sigma_guard(noise_sigma):
    if type(noise_sigma) not in (int,float) or not 0<=noise_sigma<=.2 or not math.isfinite(noise_sigma):raise ValueError("sigma必须是[0,.2]内有限反射率单位，0表示无扰动")

def _repeats_guard(repeats):
    if type(repeats) is not int or not 20<=repeats<=120:raise ValueError("条件重复须为20–120次")

def whitening_from_covariance(covariance,band_count):
    """Cholesky factor for joint draws and its inverse for whitened fitting."""
    covariance=np.asarray(covariance,dtype=float)
    if covariance.shape!=(band_count,band_count) or not np.isfinite(covariance).all():raise ValueError("空白校准协方差与波段数不匹配或含非有限值")
    try:L=np.linalg.cholesky(covariance)
    except np.linalg.LinAlgError:raise ValueError("空白校准协方差不是正定矩阵，无法生成联合噪声")
    W=whitening_matrix(L)
    return L,W

def whitening_matrix(cholesky_factor):
    try:W=np.linalg.inv(cholesky_factor)
    except np.linalg.LinAlgError:raise ValueError("空白校准协方差的Cholesky因子不可逆")
    if not np.isfinite(W).all():raise ValueError("空白校准白化矩阵含非有限值")
    return W

def conditional_refits(A,y,noise_sigma=.005,repeats=80,seed=2026,calibration=None):
    """Conditional refits under independent (legacy) or blank-calibrated joint noise.

    ``calibration`` must be a validated decoded frozen calibration. An invalid
    one raises; it never silently falls back to independent noise.
    """
    _repeats_guard(repeats)
    observed=np.asarray(y,dtype=float)
    rng=np.random.default_rng(seed)
    if calibration is None:
        _sigma_guard(noise_sigma)
        point=fit_simplex(A,observed)
        weights=[];rss=[]
        for noise in rng.normal(0,noise_sigma,size=(repeats,len(observed))):
            fitted=fit_simplex(A,observed+noise);weights.append(fitted['weights']);rss.append(fitted['rss'])
        result={"point_fit":point,"replicate_weights":weights,"replicate_rss":rss,"noise_model":"legacy-independent","noise_sigma":noise_sigma,"repeats":repeats,"degenerate_noise":noise_sigma==0,
            "interval_note":"2.5/97.5%分位范围条件于固定端元与给定sigma；对观测谱加独立Gaussian扰动重拟合，不覆盖端元误差，也不保证真配比覆盖。"}
    else:
        covariance=np.asarray(calibration['covariance'],dtype=float)
        if covariance.shape!=(len(observed),len(observed)):raise ValueError("空白校准协方差与观测波段数不匹配")
        L,W=whitening_from_covariance(covariance,len(observed))
        point=fit_simplex(A,observed,whitening=W)
        weights=[];rss=[];objectives=[];replicate_noise=[]
        for z in rng.normal(0,1,size=(repeats,len(observed))):
            noise=L@z
            fitted=fit_simplex(A,observed+noise,whitening=W)
            weights.append(fitted['weights']);rss.append(fitted['rss']);objectives.append(fitted['weighted_objective'])
            replicate_noise.append(noise.tolist())
        result={"point_fit":point,"replicate_weights":weights,"replicate_rss":rss,"noise_model":"blank-joint","noise_sigma":None,"repeats":repeats,"degenerate_noise":False,
            "calibration":{"id":calibration.get('id'),"rule_version":calibration['rule_version'],"source_hash":calibration['source_hash'],"calibration_hash":calibration['calibration_hash'],"effective_measurements":calibration['effective_measurements'],"degrees_of_freedom":calibration['degrees_of_freedom'],"noise_rms":calibration['noise_rms'],"condition_number":calibration['condition_number']},
            "replicate_noise":replicate_noise,"replicate_weighted_objective":objectives,
            "interval_note":f"2.5/97.5%分位范围条件于固定端元与空白联合噪声（校准#{calibration.get('id')}，有效测量数{calibration['effective_measurements']}，协方差自由度{calibration['degrees_of_freedom']}）；按波段相关协方差生成扰动并做广义最小二乘重拟合，不覆盖端元误差，也不保证真配比覆盖。"}
    samples=np.asarray(weights)
    result["lower"]=np.quantile(samples,.025,axis=0,method='linear').tolist()
    result["median"]=np.quantile(samples,.5,axis=0,method='linear').tolist()
    result["upper"]=np.quantile(samples,.975,axis=0,method='linear').tolist()
    return result
