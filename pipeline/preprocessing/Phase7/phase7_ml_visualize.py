"""
Phase 7-ML 결과 시각화 — 신뢰도 등급/교차 대조/타임라인/박스플롯 6종 차트.

입력: phase7_ml/summary, predictions, cross_validation, confidence_grades
출력: phase7_ml/figures/01~06_*.png
"""

import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def load_all_data(ml_dir):
    """Phase 7-ML 결과를 전부 로드한다."""
    ml_dir = Path(ml_dir)

    summary = pd.read_csv(ml_dir / "phase7_ml_summary.csv")

    predictions = []
    for f in sorted(os.listdir(ml_dir / "predictions")):
        if f.endswith(".csv"):
            df = pd.read_csv(ml_dir / "predictions" / f)
            df["date"] = pd.to_datetime(df["date"])
            predictions.append(df)
    pred_all = pd.concat(predictions, ignore_index=True)

    cross_vals = []
    for f in sorted(os.listdir(ml_dir / "cross_validation")):
        if f.endswith(".csv"):
            df = pd.read_csv(ml_dir / "cross_validation" / f)
            df["date"] = pd.to_datetime(df["date"])
            cross_vals.append(df)
    cv_all = pd.concat(cross_vals, ignore_index=True)

    grades = []
    for f in sorted(os.listdir(ml_dir / "confidence_grades")):
        if f.endswith(".csv"):
            df = pd.read_csv(ml_dir / "confidence_grades" / f)
            df["date"] = pd.to_datetime(df["date"])
            grades.append(df)
    gr_all = pd.concat(grades, ignore_index=True)

    return summary, pred_all, cv_all, gr_all


def plot_grade_distribution(cv_all, fig_dir):
    """신뢰도 등급 파이 차트 + 막대 차트."""
    stat_yes_ml_yes = (cv_all["stat_detected"] & cv_all["ml_detected"]).sum()
    stat_yes_ml_no = (cv_all["stat_detected"] & ~cv_all["ml_detected"]).sum()
    stat_no_ml_yes = (~cv_all["stat_detected"] & cv_all["ml_detected"]).sum()
    stat_no_ml_no = (~cv_all["stat_detected"] & ~cv_all["ml_detected"]).sum()

    labels = ["high\n(stat+ML)", "medium\n(stat only)", "reference\n(ML only)", "normal\n(none)"]
    values = [stat_yes_ml_yes, stat_yes_ml_no, stat_no_ml_yes, stat_no_ml_no]
    colors = ["#d32f2f", "#ff9800", "#2196f3", "#e0e0e0"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    db_values = values[:3]
    db_labels = labels[:3]
    db_colors = colors[:3]
    ax1.pie(db_values, labels=db_labels, colors=db_colors, autopct="%1.1f%%",
            startangle=90, textprops={"fontsize": 10})
    ax1.set_title(f"DB 적재 대상 ({sum(db_values)}건)", fontsize=13, fontweight="bold")

    bars = ax2.bar(labels, values, color=colors, edgecolor="black", linewidth=0.5)
    for bar, val in zip(bars, values):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 30,
                 str(val), ha="center", fontsize=10, fontweight="bold")
    ax2.set_ylabel("건수", fontsize=11)
    ax2.set_title("신뢰도 등급 분포 (전체)", fontsize=13, fontweight="bold")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(fig_dir / "01_grade_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("[시각화] 01_grade_distribution.png 저장")


def plot_grade_by_commodity(summary, fig_dir):
    """품목별 가로 누적 막대 차트."""
    cid_stats = summary.groupby("commodity_id")[
        ["grade_high", "grade_medium", "grade_reference"]
    ].sum()
    cid_stats = cid_stats.sort_values("grade_high", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 6))

    y = range(len(cid_stats))
    high = cid_stats["grade_high"].values
    medium = cid_stats["grade_medium"].values
    ref = cid_stats["grade_reference"].values

    ax.barh(y, high, color="#d32f2f", label="high", edgecolor="white", linewidth=0.5)
    ax.barh(y, medium, left=high, color="#ff9800", label="medium", edgecolor="white", linewidth=0.5)
    ax.barh(y, ref, left=high + medium, color="#2196f3", label="reference", edgecolor="white", linewidth=0.5)

    ax.set_yticks(y)
    ax.set_yticklabels(cid_stats.index, fontsize=10)
    ax.set_xlabel("건수", fontsize=11)
    ax.set_title("품목별 신뢰도 등급 분포", fontsize=13, fontweight="bold")
    ax.legend(loc="lower right", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(fig_dir / "02_grade_by_commodity.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("[시각화] 02_grade_by_commodity.png 저장")


def plot_consensus_distribution(pred_all, fig_dir):
    """3종 모델 합의 수 분포 막대 차트."""
    consensus = pred_all["ml_consensus_count"].value_counts().sort_index()

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ["#4caf50", "#ffeb3b", "#ff9800", "#d32f2f"]
    labels_map = {0: "0개\n(정상)", 1: "1개\n(미확정)", 2: "2개\n(탐지)", 3: "3개\n(전원합의)"}

    bars = ax.bar(
        [labels_map.get(i, str(i)) for i in consensus.index],
        consensus.values,
        color=[colors[i] for i in consensus.index],
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, val in zip(bars, consensus.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 20,
                f"{val}\n({val/len(pred_all)*100:.1f}%)",
                ha="center", fontsize=9)

    ax.set_ylabel("건수", fontsize=11)
    ax.set_title("3종 모델 합의 수 분포", fontsize=13, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(fig_dir / "03_consensus_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("[시각화] 03_consensus_distribution.png 저장")


def plot_cross_validation_heatmap(cv_all, fig_dir):
    """통계-ML 교차표 히트맵."""
    stat_yes_ml_yes = (cv_all["stat_detected"] & cv_all["ml_detected"]).sum()
    stat_yes_ml_no = (cv_all["stat_detected"] & ~cv_all["ml_detected"]).sum()
    stat_no_ml_yes = (~cv_all["stat_detected"] & cv_all["ml_detected"]).sum()
    stat_no_ml_no = (~cv_all["stat_detected"] & ~cv_all["ml_detected"]).sum()

    matrix = np.array([[stat_yes_ml_yes, stat_yes_ml_no],
                       [stat_no_ml_yes, stat_no_ml_no]])

    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["ML 탐지", "ML 미탐지"], fontsize=11)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["통계 탐지", "통계 미탐지"], fontsize=11)

    grade_labels = [["high", "medium"], ["reference", "normal"]]
    for i in range(2):
        for j in range(2):
            color = "white" if matrix[i, j] > 1000 else "black"
            ax.text(j, i, f"{matrix[i, j]}\n({grade_labels[i][j]})",
                    ha="center", va="center", fontsize=12, fontweight="bold", color=color)

    ax.set_title("통계-ML 교차 대조", fontsize=13, fontweight="bold")
    fig.colorbar(im, ax=ax, shrink=0.8)

    plt.tight_layout()
    plt.savefig(fig_dir / "04_cross_validation_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("[시각화] 04_cross_validation_heatmap.png 저장")


def plot_timeline(pred_all, cv_all, cid, seg, fig_dir):
    """개별 품목x구간의 탐지 타임라인."""
    pred = pred_all[(pred_all["commodity_id"] == cid) & (pred_all["segment"] == seg)].copy()
    cv = cv_all[(cv_all["commodity_id"] == cid) & (cv_all["segment"] == seg)].copy()

    if len(pred) == 0:
        return

    fig, axes = plt.subplots(4, 1, figsize=(16, 10), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1, 1, 1]})

    dates = pred["date"]

    ax = axes[0]
    ax.plot(dates, pred["if_score"], label="IF score", color="#1976d2", alpha=0.7, linewidth=0.8)
    ax.plot(dates, pred["lof_score"], label="LOF score", color="#388e3c", alpha=0.7, linewidth=0.8)
    ax.plot(dates, pred["svm_score"], label="SVM score", color="#f57c00", alpha=0.7, linewidth=0.8)
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)
    ax.set_ylabel("Anomaly Score", fontsize=9)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title(f"{cid} {seg} - ML 탐지 타임라인", fontsize=12, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax = axes[1]
    for idx, (model, color) in enumerate([("if_anomaly", "#1976d2"),
                                           ("lof_anomaly", "#388e3c"),
                                           ("svm_anomaly", "#f57c00")]):
        anomaly_dates = dates[pred[model] == True]
        ax.scatter(anomaly_dates, [idx] * len(anomaly_dates), c=color, s=8, marker="s")
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["IF", "LOF", "SVM"], fontsize=9)
    ax.set_ylabel("모델별 탐지", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax = axes[2]
    ml_dates = dates[pred["ml_detected"] == True]
    ax.scatter(ml_dates, [0] * len(ml_dates), c="#d32f2f", s=12, marker="s", label="ml_detected")
    ax.set_yticks([0])
    ax.set_yticklabels(["ML"], fontsize=9)
    ax.set_ylabel("앙상블", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax = axes[3]
    grade_colors = {"high": "#d32f2f", "medium": "#ff9800", "reference": "#2196f3"}
    cv_merged = pred[["date"]].reset_index(drop=True).merge(
        cv[["date", "stat_detected", "ml_detected"]], on="date", how="left"
    )

    dates_arr = dates.values
    for grade, color in grade_colors.items():
        if grade == "high":
            mask = cv_merged["stat_detected"].fillna(False) & cv_merged["ml_detected"].fillna(False)
        elif grade == "medium":
            mask = cv_merged["stat_detected"].fillna(False) & ~cv_merged["ml_detected"].fillna(False)
        else:
            mask = ~cv_merged["stat_detected"].fillna(False) & cv_merged["ml_detected"].fillna(False)
        grade_dates = dates_arr[mask.values]
        ax.scatter(grade_dates, [0] * len(grade_dates), c=color, s=12, marker="s", label=grade)

    ax.set_yticks([0])
    ax.set_yticklabels(["등급"], fontsize=9)
    ax.set_ylabel("신뢰도", fontsize=9)
    ax.legend(loc="upper right", fontsize=8, ncol=3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(fig_dir / f"05_timeline_{cid}_{seg}.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[시각화] 05_timeline_{cid}_{seg}.png 저장")


def plot_score_boxplot(pred_all, fig_dir):
    """모델별 이상 점수 분포 박스플롯."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    for ax, (model, score_col, color, label) in zip(axes, [
        ("if_anomaly", "if_score", "#1976d2", "Isolation Forest"),
        ("lof_anomaly", "lof_score", "#388e3c", "LOF"),
        ("svm_anomaly", "svm_score", "#f57c00", "One-Class SVM"),
    ]):
        normal = pred_all[pred_all[model] == False][score_col]
        anomaly = pred_all[pred_all[model] == True][score_col]

        bp = ax.boxplot(
            [normal.dropna(), anomaly.dropna()],
            labels=["Normal", "Anomaly"],
            patch_artist=True,
            widths=0.5,
        )
        bp["boxes"][0].set_facecolor("#e8e8e8")
        bp["boxes"][1].set_facecolor(color)
        bp["boxes"][1].set_alpha(0.6)

        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_ylabel("Score", fontsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    plt.suptitle("모델별 이상 점수 분포 (Normal vs Anomaly)", fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(fig_dir / "06_score_boxplot.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("[시각화] 06_score_boxplot.png 저장")


def run_visualize(ml_dir):
    """Phase 7-ML 시각화 전체 실행."""
    ml_dir = Path(ml_dir)
    fig_dir = ml_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    print("[시각화] 데이터 로드 중...")
    summary, pred_all, cv_all, gr_all = load_all_data(ml_dir)
    print(f"[시각화] 로드 완료: predictions={len(pred_all)}, cross_val={len(cv_all)}, grades={len(gr_all)}")
    print()

    plot_grade_distribution(cv_all, fig_dir)
    plot_grade_by_commodity(summary, fig_dir)
    plot_consensus_distribution(pred_all, fig_dir)
    plot_cross_validation_heatmap(cv_all, fig_dir)

    timeline_targets = [
        ("wheat", "A"), ("beef", "B"), ("banana", "A"),
        ("sugar", "A"), ("palmoil", "B"), ("coffee", "A"),
    ]
    for cid, seg in timeline_targets:
        plot_timeline(pred_all, cv_all, cid, seg, fig_dir)

    plot_score_boxplot(pred_all, fig_dir)

    print()
    print(f"[시각화] 전체 완료. 저장 위치: {fig_dir}")


if __name__ == "__main__":
    ML_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed", "phase7_ml"
    )
    run_visualize(ML_DIR)
