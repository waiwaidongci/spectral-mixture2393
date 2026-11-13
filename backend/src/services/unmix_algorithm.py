"""Global simplex-constrained least squares by exhaustive nonempty supports (2..6 endmembers)."""
from itertools import combinations
import numpy as np
CONDITION_LIMIT=1e6
FEASIBILITY_TOL=1e-10

def matrix_diagnostics(A):
    try:A=np.asarray(A,dtype=float)
    except (TypeError,ValueError,OverflowError):raise ValueError("端元矩阵必须为有限数字")
    if A.ndim!=2 or not 2<=A.shape[1]<=6 or not 2<=A.shape[0]<=64:raise ValueError("矩阵要求2–64波段、2–6端元，列为端元")
    if not np.isfinite(A).all() or np.max(np.abs(A))>1000:raise ValueError("端元谱包含非有限或超范围数值")
    augmented=np.vstack([A,np.ones(A.shape[1])]);singular=np.linalg.svd(augmented,compute_uv=False)
    rank=int(np.sum(singular>max(augmented.shape)*np.finfo(float).eps*singular[0]));raw_condition=float(singular[0]/singular[-1]) if singular[-1]>0 else float('inf')
    condition=raw_condition if np.isfinite(raw_condition) else None
    supported=rank==A.shape[1] and raw_condition<=CONDITION_LIMIT
    reason="增广[A;1]满列秩，支持固定端元下的唯一配比解释" if supported else "增广[A;1]秩亏，配比可能非唯一，拒绝唯一成分解释" if rank<A.shape[1] else "增广[A;1]病态，条件数超过1e6，拒绝不稳定配比解释"
    return A,{"augmented_rank":rank,"condition_number":condition,"condition_limit":CONDITION_LIMIT,"supported":supported,"reason":reason}

def whitened_augmented_condition(A,whitening):
    """Condition guard for the constrained solve after covariance whitening."""
    Aw=np.asarray(whitening,dtype=float)@np.asarray(A,dtype=float)
    augmented=np.vstack([Aw,np.ones(A.shape[1])]);singular=np.linalg.svd(augmented,compute_uv=False)
    return float(singular[0]/singular[-1]) if singular[-1]>0 and np.isfinite(singular).all() else float('inf')

def fit_simplex(A,y,*,diagnostics=None,whitening=None):
    if diagnostics is None:A,diagnostics=matrix_diagnostics(A)
    else:
        A=np.asarray(A,dtype=float)
        if A.ndim!=2 or not np.isfinite(A).all():raise ValueError("端元矩阵必须为有限二维数字")
    if not diagnostics['supported']:raise ValueError(diagnostics['reason'])
    try:y=np.asarray(y,dtype=float)
    except (TypeError,ValueError,OverflowError):raise ValueError("混合谱必须为有限数字")
    if y.shape!=(A.shape[0],) or not np.isfinite(y).all() or np.max(np.abs(y))>1000:raise ValueError("混合谱长度不匹配或包含非有限/超范围数值")
    # The constrained KKT system is solved in the whitened space when a blank
    # calibration supplies a joint covariance; reconstruction stays in reflectance.
    if whitening is None:
        Aw,yw=A,y
    else:
        W=np.asarray(whitening,dtype=float)
        if W.shape!=(A.shape[0],A.shape[0]) or not np.isfinite(W).all():raise ValueError("噪声白化矩阵与端元波段数不匹配或含非有限值")
        Aw=W@A;yw=W@y
        if not np.isfinite(Aw).all() or not np.isfinite(yw).all():raise ValueError("白化后的端元或观测含非有限值")
        condition=whitened_augmented_condition(A,W)
        if not np.isfinite(condition) or condition>CONDITION_LIMIT:raise ValueError(f"空白协方差加权后的增广矩阵条件数{condition:.3g}超过{CONDITION_LIMIT:.0e}，拒绝不稳定配比")
    m=A.shape[1];best=None;tested=0
    for size in range(1,m+1):
        for support in combinations(range(m),size):
            S=Aw[:,support]
            # Equality-constrained KKT solution via an orthonormal null space.
            # Avoid forming A.T@A, which squares the condition number.
            origin=np.full(size,1/size)
            if size==1:local=origin
            else:
                _,_,vh=np.linalg.svd(np.ones((1,size)),full_matrices=True)
                basis=vh[1:].T
                try:coordinates=np.linalg.lstsq(S@basis,yw-S@origin,rcond=None)[0]
                except np.linalg.LinAlgError:continue
                local=origin+basis@coordinates
            tested+=1;weights=np.zeros(m);weights[list(support)]=local
            if weights.min() < -FEASIBILITY_TOL or abs(weights.sum()-1)>1e-8:continue
            weights=np.maximum(weights,0.);weights/=weights.sum()
            whitened_residual=Aw@weights-yw;objective=float(np.sum(whitened_residual**2))
            if best is None or objective<best['objective']:best={"weights":weights,"objective":objective,"multiplier":float(-np.mean(2*S.T@whitened_residual))}
    if best is None:raise ValueError("没有数值可行的非负和为1解")
    weights=best['weights'];gradient=2*Aw.T@(Aw@weights-yw)+best['multiplier'];active=weights>1e-8
    scale=1+np.linalg.norm(Aw)**2+np.linalg.norm(Aw)*np.linalg.norm(yw);tol=1e-8*scale
    active_error=float(np.max(np.abs(gradient[active]))) if active.any() else 0.
    inactive_min=float(np.min(gradient[~active])) if (~active).any() else None
    if active_error>tol or (inactive_min is not None and inactive_min < -tol):raise ValueError("完整KKT最优性校验未通过；不输出不可靠配比")
    reconstructed=A@weights;residual=y-reconstructed;raw_rss=float(np.sum(residual**2))
    result={"weights":weights.tolist(),"reconstructed":reconstructed.tolist(),"residual":residual.tolist(),"rss":raw_rss,"rmse":float(np.sqrt(raw_rss/len(y))),"active_count":int(np.sum(weights>1e-8)),"equality_error":abs(float(weights.sum())-1),"active_stationarity_error":active_error,"inactive_slack_min":inactive_min,"kkt_tolerance":float(tol),"supports_solved":tested,"diagnostics":diagnostics}
    if whitening is not None:result["weighted_objective"]=best['objective']
    return result
