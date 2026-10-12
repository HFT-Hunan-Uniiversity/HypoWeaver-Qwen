import time
import numpy as np
from ..errors import AppError
from .preparation import prepare, demean


def permutation(spec, raw, progress=None):
    started = time.perf_counter()
    clean, _, _, _, paths = prepare(spec, raw)
    grid = paths.pivot(index="unit", columns="time", values="treatment").dropna()
    grid = grid.loc[grid.index.isin(clean["unit"].unique())]
    clean = clean.loc[clean["unit"].isin(grid.index)].copy()
    if grid.shape[0] < 3 or clean.empty:
        raise AppError("permutation_empty", "置换需要至少三个具有完整处理轨迹的个体")
    units = grid.index.get_indexer(clean["unit"])
    times = grid.columns.get_indexer(clean["time"])
    trajectories = grid.to_numpy(float)
    moderator = clean["moderator"].to_numpy() if spec.method_family == "mechanism_boundary" and spec.moderator else None
    y = demean(clean["y"], clean["unit"], clean["time"], spec.fe)
    m = demean(moderator, clean["unit"], clean["time"], spec.fe) if moderator is not None else None

    def coefficients(raw_d):
        raw_d = raw_d.reshape(len(clean), -1)
        d = demean(raw_d, clean["unit"], clean["time"], spec.fe)
        if moderator is None:
            denominator = (d * d).sum(axis=0)
            return np.divide(y @ d, denominator, out=np.full(d.shape[1], np.nan), where=denominator > 1e-12)
        # Frisch–Waugh–Lovell: retain D and M main effects while testing D×M.
        z = demean(raw_d * moderator[:, None], clean["unit"], clean["time"], spec.fe)
        dd, mm, dm = (d * d).sum(axis=0), float(m @ m), m @ d
        dy, my, zy, zd, zm = y @ d, float(m @ y), y @ z, (z * d).sum(axis=0), m @ z
        determinant = dd * mm - dm**2
        with np.errstate(divide="ignore", invalid="ignore"):
            numerator = zy - zd * (mm * dy - dm * my) / determinant - zm * (dd * my - dm * dy) / determinant
            denominator = (z * z).sum(axis=0) - (mm * zd**2 - 2 * dm * zd * zm + dd * zm**2) / determinant
            return np.where((determinant > 1e-12) & (denominator > 1e-12), numerator / denominator, np.nan)

    observed = float(coefficients(trajectories[units, times])[0])
    if not np.isfinite(observed):
        raise AppError("permutation_constant", "无控制变量置换模型缺少有效变异或必要主效应共线")
    rng = np.random.default_rng(spec.permutation.seed)
    values = []
    for start in range(0, spec.permutation.n, 64):
        count = min(64, spec.permutation.n - start)
        orders = np.array([rng.permutation(len(grid)) for _ in range(count)])
        draws = trajectories[orders[:, units], times].T
        estimates = coefficients(draws)
        values.extend(estimates[np.isfinite(estimates)].tolist())
        if progress:
            progress(f"置换检验 {start + count} / {spec.permutation.n}")
    if not values:
        raise AppError("permutation_constant", "置换后的处理轨迹均缺少有效变异")
    distribution = np.array(values)
    p = float((1 + (np.abs(distribution) >= abs(observed)).sum()) / (len(values) + 1))
    return {
        "p": p,
        "n": len(values),
        "requested_n": spec.permutation.n,
        "seed": spec.permutation.seed,
        "observed": observed,
        "distribution": values,
        "n_obs": len(clean),
        "n_units": int(clean["unit"].nunique()),
        "excluded_incomplete_units": int(paths["unit"].nunique() - len(grid)),
        "distribution_summary": {
            "mean": float(distribution.mean()),
            "std": float(distribution.std()),
            "q025": float(np.quantile(distribution, 0.025)),
            "q975": float(np.quantile(distribution, 0.975)),
        },
        "elapsed_seconds": time.perf_counter() - started,
        ("note"): (
            "在个体间置换整条处理轨迹；固定效应去均值，不含控制变量；交互模型保留处理及调节变量主效应。双侧加一校正。"
        ),
    }
