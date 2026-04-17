import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import yaml
from sklearn.cluster import KMeans
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, silhouette_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

RANDOM_STATE = 42
DATA_PATH = Path(r"data/sample/cardio_sample.csv")
OUT_DIR = Path(r"outputs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_COL = "Успех_реабилитации_01"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cardio digital twin pipeline.")
    parser.add_argument("--config", type=str, default="configs/config.yaml", help="Path to YAML config.")
    return parser.parse_args()


def load_config(path: str) -> Dict:
    cfg_path = Path(path)
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, encoding="cp1251")
    df = df.dropna(how="all")
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df[df[TARGET_COL].notna()].copy()
    return df


def choose_k(X: pd.DataFrame, k_min: int = 2, k_max: int = 6) -> Tuple[int, Dict[int, float], Pipeline]:
    prep = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
    X_scaled = prep.fit_transform(X)
    scores = {}
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=20)
        labels = km.fit_predict(X_scaled)
        scores[k] = float(silhouette_score(X_scaled, labels))
    return max(scores, key=scores.get), scores, prep


def build_models() -> Dict[str, Pipeline]:
    base = {
        "logreg": LogisticRegression(max_iter=2500, random_state=RANDOM_STATE),
        "rf": RandomForestClassifier(n_estimators=350, random_state=RANDOM_STATE, class_weight="balanced"),
        "gb": GradientBoostingClassifier(random_state=RANDOM_STATE),
    }
    out = {}
    for name, est in base.items():
        out[name] = Pipeline(
            [("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("clf", est)]
        )
    return out


def evaluate_model(pipe: Pipeline, X_train: pd.DataFrame, y_train: pd.Series, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, float]:
    pipe.fit(X_train, y_train)
    pred = pipe.predict(X_test)
    prob = pipe.predict_proba(X_test)[:, 1]
    return {
        "accuracy": float(accuracy_score(y_test, pred)),
        "f1": float(f1_score(y_test, pred)),
        "roc_auc": float(roc_auc_score(y_test, prob)),
    }


def select_best_per_cluster(df: pd.DataFrame, cluster_col: str) -> Dict[int, Dict]:
    result = {}
    models = build_models()
    for c in sorted(df[cluster_col].unique()):
        part = df[df[cluster_col] == c].copy()
        X = part.drop(columns=[TARGET_COL, cluster_col])
        y = pd.to_numeric(part[TARGET_COL], errors="coerce").fillna(0).astype(int)
        x_tr, x_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=y)
        best_name, best_model, best_metrics, best_auc = None, None, None, -1.0
        for name, model in models.items():
            m = evaluate_model(model, x_tr, y_tr, x_te, y_te)
            if m["roc_auc"] > best_auc:
                best_name, best_model, best_metrics, best_auc = name, model, m, m["roc_auc"]
        best_model.fit(X, y)
        result[int(c)] = {"model_name": best_name, "metrics": best_metrics, "model": best_model}
    return result


def classify_risk(row: pd.Series) -> str:
    score = 0
    score += int(row["ФВ_ЛЖ_%"] < 45)
    score += int(row["SpO2_%"] < 93)
    score += int(row["6MWT_метры"] < 380)
    score += int(row["TUG_сек"] > 12)
    score += int(row["GNRI_баллы"] < 90)
    score += int(row["mFI_01"] > 0.30)
    score += int(row["HADS_баллы"] > 12)
    if score >= 4:
        return "high"
    if score >= 2:
        return "moderate"
    return "low"


def base_plan_by_risk(risk: str) -> Dict[str, float]:
    if risk == "high":
        return {"intensity": 0.50, "sessions": 3, "minutes": 25}
    if risk == "moderate":
        return {"intensity": 0.62, "sessions": 4, "minutes": 35}
    return {"intensity": 0.74, "sessions": 5, "minutes": 45}


def apply_week_step(state: pd.Series, plan: Dict[str, float]) -> pd.Series:
    s = state.copy()
    intensity = plan["intensity"]
    sessions = plan["sessions"]
    minutes = plan["minutes"]
    s["Физактив_мин"] += sessions * minutes * 0.85
    s["Шаги_день"] += int(250 * sessions * intensity)
    s["6MWT_метры"] += max(2, int(7 * intensity * sessions))
    s["TUG_сек"] = max(3.5, s["TUG_сек"] - 0.09 * sessions * intensity)
    s["SRT_баллы"] = min(10.0, s["SRT_баллы"] + 0.06 * sessions)
    s["SpO2_%"] = min(99.0, s["SpO2_%"] + 0.03 * sessions)
    s["HADS_баллы"] = max(2.0, s["HADS_баллы"] - 0.05 * sessions)
    s["QoR15_баллы"] = min(150.0, s["QoR15_баллы"] + 0.8 * sessions)
    s["ВАШ_одышки_010"] = max(0.0, s["ВАШ_одышки_010"] - 0.05 * sessions)
    s["ВАШ_боли_010"] = max(0.0, s["ВАШ_боли_010"] - 0.04 * sessions)
    safety_penalty = 0
    if s["SpO2_%"] < 92:
        safety_penalty += 1
    if s["ЧСС_удмин"] > 105 and intensity > 0.7:
        safety_penalty += 1
    if s["Лактат_ммольл"] > 3.0 and intensity > 0.65:
        safety_penalty += 1
    s["_safety_penalty"] = safety_penalty
    return s


def objective(prob: float, state: pd.Series, penalty: float) -> float:
    gain = (state["6MWT_метры"] / 500) + (130 - state["TUG_сек"]) / 130 + (state["QoR15_баллы"] / 140)
    return 0.60 * prob + 0.30 * gain - 0.10 * penalty


def simulate_twin(cluster_df: pd.DataFrame, model: Pipeline, cluster_id: int) -> Dict:
    numeric = [c for c in cluster_df.columns if c != TARGET_COL]
    center = cluster_df[numeric].mean()
    idx = ((cluster_df[numeric].sub(center, axis=1) ** 2).sum(axis=1)).idxmin()
    patient = cluster_df.loc[idx].drop(labels=[TARGET_COL]).copy()
    patient = patient.fillna(cluster_df.drop(columns=[TARGET_COL]).median(numeric_only=True))
    risk = classify_risk(patient)
    base = base_plan_by_risk(risk)
    candidates = []
    for inten in np.linspace(max(0.4, base["intensity"] - 0.12), min(0.85, base["intensity"] + 0.12), 5):
        for sess in [max(2, base["sessions"] - 1), base["sessions"], base["sessions"] + 1]:
            for mins in [max(20, base["minutes"] - 10), base["minutes"], min(60, base["minutes"] + 10)]:
                candidates.append({"intensity": float(round(inten, 2)), "sessions": int(sess), "minutes": int(mins)})
    best, best_trace = None, None
    for plan in candidates:
        st, total_penalty, trace = patient.copy(), 0.0, []
        for week in range(1, 13):
            st = apply_week_step(st, plan)
            total_penalty += st.get("_safety_penalty", 0.0)
            features = pd.DataFrame([st.drop(labels=["_safety_penalty"])])
            prob = float(model.predict_proba(features)[:, 1][0])
            score = objective(prob, st, total_penalty)
            trace.append(
                {
                    "week": week,
                    "prob_success": round(prob, 4),
                    "6MWT": round(float(st["6MWT_метры"]), 2),
                    "TUG": round(float(st["TUG_сек"]), 2),
                    "QoR15": round(float(st["QoR15_баллы"]), 2),
                    "safety_penalty": round(float(total_penalty), 2),
                    "score": round(float(score), 4),
                }
            )
        if (best is None) or (trace[-1]["score"] > best["final_score"]):
            best, best_trace = {"plan": plan, "final_score": trace[-1]["score"], "risk": risk}, trace
    return {"cluster": cluster_id, "risk": best["risk"], "best_plan": best["plan"], "trace": best_trace, "baseline_patient": patient.to_dict()}


def update_model_with_simulation(model: Pipeline, cluster_data: pd.DataFrame, twin_result: Dict) -> Dict[str, float]:
    X_real = cluster_data.drop(columns=[TARGET_COL])
    y_real = pd.to_numeric(cluster_data[TARGET_COL], errors="coerce").fillna(0).astype(int)
    synth_rows, synth_y = [], []
    base = pd.Series(twin_result["baseline_patient"])
    plan = twin_result["best_plan"]
    for _ in range(250):
        st = base.copy()
        for _w in range(np.random.randint(2, 13)):
            st = apply_week_step(st, plan)
        if "_safety_penalty" in st.index:
            st = st.drop(labels=["_safety_penalty"])
        for col in st.index:
            st[col] = float(st[col]) + np.random.normal(0, 0.02 * (abs(float(st[col])) + 1))
        p = float(model.predict_proba(pd.DataFrame([st]))[:, 1][0])
        synth_rows.append(st)
        synth_y.append(int(p >= 0.5))
    X_aug = pd.concat([X_real, pd.DataFrame(synth_rows)], ignore_index=True)
    y_aug = pd.concat([y_real, pd.Series(synth_y)], ignore_index=True)
    x_tr, x_te, y_tr, y_te = train_test_split(X_real, y_real, test_size=0.25, random_state=RANDOM_STATE, stratify=y_real)
    before = evaluate_model(model, x_tr, y_tr, x_te, y_te)
    model.fit(X_aug, y_aug)
    after = evaluate_model(model, x_tr, y_tr, x_te, y_te)
    return {"before_auc": round(before["roc_auc"], 4), "after_auc": round(after["roc_auc"], 4), "before_f1": round(before["f1"], 4), "after_f1": round(after["f1"], 4)}


def make_plan_text(cluster_id: int, twin: Dict, metrics: Dict[str, float]) -> str:
    bp, p, risk = twin["baseline_patient"], twin["best_plan"], twin["risk"]
    if risk == "high":
        risk_label, hr_zone = "красный", "40-60%"
    elif risk == "moderate":
        risk_label, hr_zone = "жёлтый", "50-70%"
    else:
        risk_label, hr_zone = "зелёный", "70-85%"
    return f"""
=== План для класса {cluster_id} ===
Шаблон Персонализированной Программы Кардиореабилитации

1. Общая информация о пациенте
- Класс: {cluster_id}
- Риск: {risk_label} ({risk})
- Возраст: {bp['Возраст_лет']:.0f}; Пол(м0_ж1): {bp['Пол_м0_ж1']:.0f}
- ИМТ: {bp['ИМТ_кгм2']:.1f}; ASA: {bp['ASA_класс']:.0f}

2. Фазы программы (Phase I-IV)
Phase I (1-7 дней): ходьба 10-20 мин, {max(2, p['sessions']-1)} р/день, дыхательная гимнастика.
Phase II (1-4 нед): аэробные нагрузки {p['minutes']} мин, {p['sessions']} р/нед, {hr_zone} HR reserve.
Phase III (5-12 нед): интервалы и силовые, {p['sessions']} р/нед, {p['minutes']} мин.
Phase IV (>12 нед): домашний режим 150 мин/нед, контроль раз в квартал.

3. Правила персонализации
- Интенсивность: {p['intensity']*100:.0f}% от индивидуального максимума.
- Частота: {p['sessions']} сессий/нед.
- Длительность сессии: {p['minutes']} мин.
- Алерты: SpO2<92, лактат>3, HADS>16 -> пауза и консультация врача.

4. Алгоритм генерации плана
- Кластеризация: KMeans (K=оптимум по silhouette).
- Модель класса: ROC-AUC={metrics['roc_auc']:.3f}, F1={metrics['f1']:.3f}.
- Обновление модели после виртуальных экспериментов: AUC {metrics.get('before_auc', 0)} -> {metrics.get('after_auc', 0)}.

5. Целевые KPI на 12 недель
- 6MWT: {bp['6MWT_метры']:.0f} -> {twin['trace'][-1]['6MWT']:.0f} м
- TUG: {bp['TUG_сек']:.1f} -> {twin['trace'][-1]['TUG']:.1f} сек
- QoR15: {bp['QoR15_баллы']:.0f} -> {twin['trace'][-1]['QoR15']:.0f}
- Вероятность успеха к 12-й неделе: {twin['trace'][-1]['prob_success']:.2f}
""".strip()


def main():
    global DATA_PATH, OUT_DIR
    args = parse_args()
    cfg = load_config(args.config)
    DATA_PATH = Path(cfg.get("data_path", str(DATA_PATH)))
    OUT_DIR = Path(cfg.get("out_dir", str(OUT_DIR)))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    X = df.drop(columns=[TARGET_COL])
    best_k, sil_scores, prep = choose_k(X)
    labels = KMeans(n_clusters=best_k, random_state=RANDOM_STATE, n_init=20).fit_predict(prep.transform(X))
    dfx = df.copy()
    dfx["cluster"] = labels
    cls_models = select_best_per_cluster(dfx, "cluster")
    twins, plans, metrics_map = {}, [], {}
    for c in sorted(dfx["cluster"].unique()):
        cdf = dfx[dfx["cluster"] == c].copy().drop(columns=["cluster"])
        model = cls_models[int(c)]["model"]
        met = cls_models[int(c)]["metrics"].copy()
        twin = simulate_twin(cdf, model, int(c))
        upd = update_model_with_simulation(model, cdf, twin)
        met.update(upd)
        twins[int(c)] = twin
        metrics_map[int(c)] = met
        plans.append(make_plan_text(int(c), twin, met))
    summary = {
        "dataset_rows": int(df.shape[0]),
        "dataset_cols": int(df.shape[1]),
        "best_k": int(best_k),
        "silhouette_scores": {str(k): round(v, 4) for k, v in sil_scores.items()},
        "class_distribution": dfx["cluster"].value_counts().sort_index().to_dict(),
        "model_metrics_by_class": metrics_map,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "twin_simulations.json").write_text(json.dumps(twins, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "rehab_plans.txt").write_text("\n\n".join(plans), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
