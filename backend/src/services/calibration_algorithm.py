"""Blank-spectrum joint noise calibration.

Repeated blank readings are the only source of the measurement-noise covariance.
The rule is explicit and versioned: every replicate must carry a finite reading for
every band, the per-band mean is removed, the unbiased sample covariance is formed,
and a full-rank covariance under the condition guard is required. Anything else is
reported as invalid; it is never silently replaced by independent Gaussian noise.
"""
import math
import numpy as np
from ..utils.fingerprint import fingerprint

CALIBRATION_RULE_VERSION = "blank-joint-covariance-v1"
CALIBRATION_CONDITION_LIMIT = 1e6
MAX_BLANK_REPLICATES = 200
MAX_BANDS = 64
MAX_NOISE_RMS = 0.2


def _issue_text(issues):
    shown = "；".join(issues[:8])
    if len(issues) > 8:
        shown += f"；另有{len(issues)-8}处未列出"
    return shown


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _safe_values(value):
    if isinstance(value, list):
        return [_safe_values(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "nonfinite:" + repr(value)
    return value


def source_fingerprint(wavelengths, readings):
    """Hash of the frozen blank source, independent of the estimation rule."""
    return fingerprint({"wavelengths": [float(w) for w in wavelengths], "readings": _safe_values(readings)})


def estimate_payload(band_count, effective_measurements, degrees_of_freedom, mean, covariance, condition_number, noise_rms):
    return {
        "band_count": int(band_count),
        "effective_measurements": int(effective_measurements),
        "degrees_of_freedom": int(degrees_of_freedom),
        "mean": [float(value) for value in mean],
        "covariance": [[float(value) for value in row] for row in covariance],
        "condition_number": float(condition_number),
        "noise_rms": float(noise_rms),
    }


def calibration_fingerprint(source_hash, rule_version, estimate):
    """Hash of source + rule + fitted estimate; this is what a run freezes."""
    return fingerprint({"source_hash": source_hash, "rule_version": rule_version, "estimate": estimate})


def evaluate_blank_calibration(readings, band_count, wavelengths=None, rule_version=CALIBRATION_RULE_VERSION):
    """Inspect a blank batch and estimate the joint covariance.

    Returns a dict instead of raising for data-quality problems so the caller can
    display the explicit reason. Unexpected shapes are also folded into ``reason``.
    """
    result = {
        "rule_version": rule_version,
        "band_count": band_count if isinstance(band_count, int) else None,
        "readings_count": len(readings) if isinstance(readings, list) else 0,
        "effective_measurements": 0,
        "degrees_of_freedom": 0,
        "valid": False,
        "reason": "",
        "issues": [],
        "normalized_readings": [],
        "mean": None,
        "covariance": None,
        "condition_number": None,
        "noise_rms": None,
    }
    try:
        if not isinstance(band_count, int) or not 1 <= band_count <= MAX_BANDS:
            raise ValueError(f"空白校准需要1–{MAX_BANDS}个波段")
        if wavelengths is not None:
            waves = np.asarray(wavelengths, dtype=float)
            if waves.shape != (band_count,) or not np.isfinite(waves).all() or np.any(np.diff(waves) <= 0):
                raise ValueError("光谱库冻结的波长必须有限、严格递增且与波段数一致")
        if not isinstance(readings, list) or not readings:
            raise ValueError("空白测谱至少需要一次重复读数")
        if len(readings) > MAX_BLANK_REPLICATES:
            raise ValueError(f"空白重复最多{MAX_BLANK_REPLICATES}次，请拆分批次或减少行数")

        complete = []
        issues = []
        for index, row in enumerate(readings, start=1):
            if not isinstance(row, list):
                issues.append(f"第{index}次读数不是波段数组")
                continue
            if len(row) != band_count:
                issues.append(f"第{index}次读数含{len(row)}个值，应为{band_count}个波段（缺波段或多余波段不能静默忽略）")
                continue
            invalid = []
            for band, value in enumerate(row, start=1):
                if not _finite_number(value):
                    invalid.append(band)
                elif abs(float(value)) > 1000:
                    invalid.append(band)
            if invalid:
                issues.append(f"第{index}次读数在波段{','.join(str(b) for b in invalid)}处缺读数、非有限或超出反射率范围")
                continue
            complete.append([float(value) for value in row])

        result["issues"] = issues
        if issues:
            result["reason"] = "空白测谱含缺波段或无效读数：" + _issue_text(issues) + "；整批不用于校准，不退回独立等方差噪声"
            return result

        n = len(complete)
        result["readings_count"] = n
        result["effective_measurements"] = n
        result["degrees_of_freedom"] = n - 1
        if n - 1 < band_count:
            result["reason"] = (
                f"有效空白重复{n}次，扣除各波段均值后仅{n-1}个自由度，不足以估计{band_count}维联合协方差，"
                f"至少需要{band_count + 1}次完整重复；不退回独立等方差噪声"
            )
            return result

        matrix = np.asarray(complete, dtype=float)
        mean = matrix.mean(axis=0)
        centered = matrix - mean
        covariance = centered.T @ centered / (n - 1)
        if not np.isfinite(covariance).all():
            result["reason"] = "空白协方差含非有限值，校准不可用；不退回独立等方差噪声"
            return result
        covariance = (covariance + covariance.T) / 2
        eigenvalues = np.linalg.eigvalsh(covariance)
        largest = float(eigenvalues[-1])
        rank_tol = max(covariance.shape) * np.finfo(float).eps * max(largest, 0.0)
        if largest <= 0 or float(eigenvalues[0]) <= rank_tol:
            result["reason"] = (
                "空白协方差秩亏，或某个波段在重复间没有变化，无法区分各波段的联合噪声；"
                "不退回独立等方差噪声"
            )
            return result
        condition = largest / float(eigenvalues[0])
        if not math.isfinite(condition) or condition > CALIBRATION_CONDITION_LIMIT:
            result["reason"] = (
                f"空白协方差条件数{condition:.3g}超过{CALIBRATION_CONDITION_LIMIT:.0e}，数值上不可靠；"
                "不退回独立等方差噪声"
            )
            return result
        noise_rms = float(np.sqrt(np.trace(covariance) / band_count))
        if not math.isfinite(noise_rms) or noise_rms <= 0 or noise_rms > MAX_NOISE_RMS:
            result["reason"] = (
                f"空白噪声RMS={noise_rms:.6g}不在(0,{MAX_NOISE_RMS}]反射率范围内；"
                "请检查空白测谱单位或数据来源，不退回独立等方差噪声"
            )
            return result

        result.update(
            valid=True,
            reason=(
                f"空白重复{n}次；扣除各波段均值后估计{band_count}维联合协方差。"
                f"有效测量数{n}（协方差自由度{n-1}），噪声RMS {noise_rms:.6g}，条件数{condition:.3g}"
            ),
            normalized_readings=complete,
            effective_measurements=n,
            degrees_of_freedom=n - 1,
            mean=mean.tolist(),
            covariance=covariance.tolist(),
            condition_number=float(condition),
            noise_rms=noise_rms,
        )
    except (ValueError, TypeError, OverflowError) as exc:
        result["reason"] = str(exc)
    return result


def validate_covariance(covariance, band_count, condition_limit=CALIBRATION_CONDITION_LIMIT):
    covariance = np.asarray(covariance, dtype=float)
    if covariance.shape != (band_count, band_count):
        raise ValueError("空白校准协方差的波段数与本次光谱库不一致")
    if not np.isfinite(covariance).all():
        raise ValueError("空白校准协方差含非有限数值")
    if not np.allclose(covariance, covariance.T, rtol=1e-8, atol=1e-12):
        raise ValueError("空白校准协方差不是对称矩阵")
    eigenvalues = np.linalg.eigvalsh(covariance)
    if not np.isfinite(eigenvalues).all() or float(eigenvalues[0]) <= 0:
        raise ValueError("空白校准协方差不是正定矩阵")
    condition = float(eigenvalues[-1]) / float(eigenvalues[0])
    if not math.isfinite(condition) or condition > condition_limit:
        raise ValueError(f"空白校准协方差条件数{condition:.3g}超过{condition_limit:.0e}")
    return covariance, condition


def validate_frozen_calibration(frozen, wavelengths, rule_version=CALIBRATION_RULE_VERSION):
    """Verify and decode a calibration snapshot frozen into an existing run.

    A bad or stale frozen snapshot is a hard failure; there is deliberately no
    fallback to independent noise.
    """
    if not isinstance(frozen, dict):
        raise ValueError("运行冻结的空白校准快照缺失或格式错误")
    if frozen.get("rule_version") != rule_version:
        raise ValueError(f"该运行冻结的空白校准属于规则{str(frozen.get('rule_version'))}，当前计算规则为{rule_version}；旧运行不静默改算，请保留原规则结果或以冻结来源重算校准后新建研究")
    readings = frozen.get("readings")
    estimate = frozen.get("estimate")
    if not isinstance(readings, list) or not isinstance(estimate, dict):
        raise ValueError("空白校准快照缺少重复读数或联合噪声估计")
    try:
        waves = np.asarray(wavelengths, dtype=float)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("光谱库波长不是有限数字")
    if waves.ndim != 1 or not np.isfinite(waves).all() or np.any(np.diff(waves) <= 0):
        raise ValueError("光谱库波长必须有限且严格递增")
    band_count = len(waves)
    source_hash = frozen.get("source_hash")
    if not isinstance(source_hash, str):
        raise ValueError("空白校准快照缺少来源指纹")
    if source_fingerprint(waves, readings) != source_hash:
        raise ValueError("空白校准快照来源指纹不一致，冻结读数可能被改动")
    try:
        mean = np.asarray(estimate.get("mean"), dtype=float)
        covariance = np.asarray(estimate.get("covariance"), dtype=float)
        effective = estimate.get("effective_measurements")
        dof = estimate.get("degrees_of_freedom")
        noise_rms = estimate.get("noise_rms")
        stored_condition = estimate.get("condition_number")
    except (TypeError, ValueError, OverflowError):
        raise ValueError("空白校准快照的均值或协方差不是有限数字")
    if mean.shape != (band_count,) or covariance.shape != (band_count, band_count):
        raise ValueError("空白校准快照的波段数与本次光谱库不一致")
    if not isinstance(effective, int) or isinstance(effective, bool) or effective <= band_count:
        raise ValueError("冻结空白校准的有效测量数不足以估计联合协方差")
    if not isinstance(dof, int) or isinstance(dof, bool) or dof != effective - 1:
        raise ValueError("冻结空白校准的协方差自由度与有效测量数不一致")
    if not _finite_number(noise_rms) or not 0 < float(noise_rms) <= MAX_NOISE_RMS:
        raise ValueError("冻结空白校准的噪声RMS无效")
    covariance, condition = validate_covariance(covariance, band_count)
    if not _finite_number(stored_condition) or not math.isclose(float(stored_condition), condition, rel_tol=1e-8, abs_tol=1e-12):
        raise ValueError("冻结空白校准的条件数与协方差不一致")
    derived_rms = float(np.sqrt(np.trace(covariance) / band_count))
    if not math.isclose(derived_rms, float(noise_rms), rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError("冻结空白校准的噪声RMS与协方差不一致")
    # Rebuild the hash from the stored (JSON round-tripped) scalars so byte-identical
    # snapshots verify exactly; the consistency checks above guard their meaning.
    payload = estimate_payload(band_count, effective, dof, mean, covariance, stored_condition, noise_rms)
    if calibration_fingerprint(source_hash, rule_version, payload) != frozen.get("calibration_hash"):
        raise ValueError("空白校准快照指纹不一致，冻结估计可能被改动")
    return {
        "id": frozen.get("id"),
        "rule_version": rule_version,
        "source_hash": source_hash,
        "calibration_hash": frozen.get("calibration_hash"),
        "readings_count": frozen.get("readings_count"),
        "effective_measurements": effective,
        "degrees_of_freedom": dof,
        "band_count": band_count,
        "mean": mean,
        "covariance": covariance,
        "condition_number": condition,
        "noise_rms": derived_rms,
        "readings": readings,
    }
