"""Random search for the LightGBM settings, on a few validation folds only.

Plan (see notebooks/quality_inspect_decision.md)
  tuning folds  fold03, fold04, fold07, fold08: the only folds that influence the choice of settings.
  check folds   the other six: used afterwards to see whether the gain is real.
  test block    never loaded.
Each trial is scored by the mean WAPE over {pooled, leave-one-building-out} x {horizon 6, horizon 24}
on the tuning folds, residual target. One shared setting is chosen for all horizons.
Trial 0 is the current default settings, run through the same procedure, as the reference.

Every finished trial is appended to <out>/trials.jsonl, so a stopped run can be resumed (same seed and
output folder) and the file can be copied back from another machine.

Usage
  python -m modeling.tuning search  [--trials 30] [--seed 0] [--out results/tuning] [--workers 3] [--threads 4]
  python -m modeling.tuning confirm [--out results/tuning] [--workers 3] [--threads 4]
"""
import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from etl import windows as w
from modeling import gbm, metrics

TUNE_FOLDS = ("fold03", "fold04", "fold07", "fold08")
TUNE_HORIZONS = (6, 24)
TUNE_TARGET = "residual"
SCHEMES = ("pooled", "lobo")
STOP_DAYS = gbm.STOP_DAYS


def sample_params(seed: int, trial: int) -> dict:
    """Settings of one trial. Trial 0 is the default; the rest are drawn at random from (seed, trial)."""
    if trial == 0:
        keys = ("objective", "num_leaves", "min_child_samples", "subsample", "colsample_bytree", "reg_lambda")
        return {k: gbm.PARAMS[k] for k in keys}
    rng = np.random.default_rng([seed, trial])
    log_uniform = lambda lo, hi: float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
    params = {
        "objective": str(rng.choice(["l1", "huber", "l2"])),
        "num_leaves": int(round(log_uniform(15, 127))),
        "min_child_samples": int(round(log_uniform(20, 400))),
        "subsample": float(rng.uniform(0.5, 1.0)),
        "colsample_bytree": float(rng.uniform(0.4, 1.0)),
        "reg_lambda": log_uniform(0.01, 30),
    }
    if params["objective"] == "huber":
        params["alpha"] = log_uniform(2_000, 30_000)    # Wh: errors below this are treated like L2, above like L1
    return params


def full_params(trial_params: dict, threads: int) -> dict:
    return {**gbm.PARAMS, **trial_params, "n_jobs": threads}


def load_data(gold: pd.DataFrame, horizons=TUNE_HORIZONS) -> tuple[dict, list]:
    """Windows of the tuning horizons (test block excluded) and the folds of the whole split."""
    folds, t0 = w.make_folds(gold.index)
    return {h: gbm.load_horizon(gold, h, t0) for h in horizons}, folds


def run_jobs(datas: dict, folds: list, params: dict, targets, schemes, workers: int, stop_days) -> pd.DataFrame:
    """All fits of one setting. LightGBM releases the GIL, so threads share the data without copies."""
    jobs = [(d, f, scheme, target, held_out)
            for d in datas.values() for f in folds for target in targets for scheme in schemes
            for held_out in ([None] if scheme == "pooled" else d.buildings)]
    results = Parallel(n_jobs=workers, prefer="threads")(
        delayed(gbm.run_fold)(d, f, scheme, target, held_out, params, stop_days) for d, f, scheme, target, held_out in jobs)
    return pd.concat([r for r in results if len(r)], ignore_index=True)


def trial_score(preds: pd.DataFrame) -> tuple[float, dict]:
    """Mean over (scheme, horizon) of the WAPE pooled over all rows of the tuning folds."""
    by = {f"{s}_h{h}": metrics.wape(g["y_true"], g["y_pred"]) for (s, h), g in preds.groupby(["scheme", "horizon"])}
    return float(np.mean(list(by.values()))), by


def evaluate_trial(datas: dict, folds: list, params: dict, workers: int = 3, stop_days=STOP_DAYS) -> dict:
    t = time.time()
    preds = run_jobs(datas, folds, params, [TUNE_TARGET], SCHEMES, workers, stop_days)
    score, by = trial_score(preds)
    return {"score": score, "wape": by, "seconds": round(time.time() - t, 1)}


def read_trials(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def search(gold: pd.DataFrame, out: Path, trials: int, seed: int, workers: int, threads: int, log=print) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "trials.jsonl"
    done = {t["trial"] for t in read_trials(path) if t["seed"] == seed}
    datas, folds = load_data(gold)
    tune = [f for f in folds if f.name in TUNE_FOLDS]
    for trial in range(trials + 1):                         # trial 0 = default settings
        if trial in done:
            continue
        trial_params = sample_params(seed, trial)
        res = evaluate_trial(datas, tune, full_params(trial_params, threads), workers)
        row = {"trial": trial, "seed": seed, "params": trial_params, **res}
        with path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        log(f"trial {trial:3d}  score {res['score']:.4f}  {res['seconds']:.0f}s  {trial_params}")
    return read_trials(path)


def best_trial(trials: list[dict]) -> dict:
    return min(trials, key=lambda t: t["score"])


def confirm(gold: pd.DataFrame, out: Path, workers: int, threads: int, log=print) -> pd.DataFrame:
    """Best settings on all 10 folds, both targets, both schemes, horizons 1, 6 and 24."""
    trials = read_trials(out / "trials.jsonl")
    best, default = best_trial(trials), next(t for t in trials if t["trial"] == 0)
    log(f"best trial {best['trial']} score {best['score']:.4f} (default {default['score']:.4f}) {best['params']}")
    params = full_params(best["params"], threads)
    datas, folds = load_data(gold, w.HORIZONS)
    preds = run_jobs(datas, folds, params, gbm.TARGETS, SCHEMES, workers, STOP_DAYS)
    preds["tuning_fold"] = preds["fold"].isin(TUNE_FOLDS)
    dest = out / "confirm"
    dest.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(dest / "predictions.parquet")
    (dest / "best_params.json").write_text(json.dumps(best, indent=1))
    for name, by in {"overall": ["scheme", "target", "horizon"], "by_group": ["tuning_fold", "scheme", "target", "horizon"],
                     "by_fold": ["scheme", "target", "horizon", "fold"]}.items():
        metrics.score_table(preds, by=by).to_csv(dest / f"{name}.csv", index=False)
    first = out.parent / "gbm" / "predictions.parquet"
    if first.exists():
        compare_to_first_run(preds, pd.read_parquet(first)).to_csv(dest / "vs_first_run.csv", index=False)
    return preds


def compare_to_first_run(tuned: pd.DataFrame, first: pd.DataFrame) -> pd.DataFrame:
    """All-season WAPE and MAE of the tuned and the first run, on the check folds and on the tuning folds."""
    rows = []
    for name, df in (("first", first), ("tuned", tuned)):
        df = df.assign(tuning_fold=df["fold"].isin(TUNE_FOLDS))
        t = metrics.score_table(df, by=["tuning_fold", "scheme", "target", "horizon"]).query("season == 'all'")
        rows.append(t.assign(run=name))
    t = pd.concat(rows).pivot(index=["tuning_fold", "scheme", "target", "horizon"], columns="run", values=["wape", "mae_kwh"])
    t.columns = [f"{m}_{r}" for m, r in t.columns]
    t["wape_change"] = t["wape_tuned"] / t["wape_first"] - 1
    return t.reset_index()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["search", "confirm"])
    ap.add_argument("--gold", default="data/gold/htot_oslo.parquet")
    ap.add_argument("--out", default="results/tuning")
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3, help="fits running side by side")
    ap.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 4) // 3), help="threads per fit")
    args = ap.parse_args()

    gold, out = pd.read_parquet(args.gold), Path(args.out)
    if args.mode == "search":
        trials = search(gold, out, args.trials, args.seed, args.workers, args.threads, log=lambda m: print(m, flush=True))
        top = sorted(trials, key=lambda t: t["score"])[:5]
        print("top trials:", *[f"{t['trial']}: {t['score']:.4f} {t['params']}" for t in top], sep="\n  ")
    else:
        confirm(gold, out, args.workers, args.threads, log=lambda m: print(m, flush=True))
        vs = out / "confirm" / "vs_first_run.csv"
        print(pd.read_csv(vs).round(3).to_string(index=False) if vs.exists() else "no first run found for comparison")


if __name__ == "__main__":
    main()
