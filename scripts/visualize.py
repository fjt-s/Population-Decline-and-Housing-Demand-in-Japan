"""analyze.py の出力（data/processed/）から、最終レポート用の図を docs/figures/ に書き出す。

前提として `python scripts/build_dataset.py` → `python scripts/analyze.py` を実行済みであること。

使い方:
    python scripts/visualize.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
FIG_DIR = Path(__file__).resolve().parent.parent / "docs" / "figures"

plt.rcParams["font.family"] = "Noto Sans CJK JP"
plt.rcParams["axes.unicode_minus"] = False

DENSITY_ORDER = [
    "1_高密度都市部(4000人/km2以上)", "2_都市部(1000-4000人/km2)",
    "3_郊外・地方都市(300-1000人/km2)", "4_農山村・過疎的(300人/km2未満)",
]
DENSITY_LABELS = ["高密度都市部\n(4000人/km2〜)", "都市部\n(1000-4000)", "郊外・地方都市\n(300-1000)", "農山村・過疎的\n(〜300人/km2)"]


def fig1_density_correlation():
    """密度区分別の相関係数（棟数ベース r / 延床面積ベース r_floor）。単調に弱まるのはr_floorだけ、
    という案1-b/cの核心の発見を1枚で示す。"""
    df = pd.read_csv(PROCESSED_DIR / "analysis1b_size_summary.csv")
    df = df.set_index("size_group").loc[DENSITY_ORDER]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = np.arange(len(DENSITY_ORDER))
    w = 0.35
    ax.bar(x - w / 2, df["pearson_r"], w, label="r（棟数ベース）", color="#94a3b8")
    ax.bar(x + w / 2, df["pearson_r_floor"], w, label="r_floor（延床面積ベース）", color="#2563eb")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(DENSITY_LABELS, fontsize=9)
    ax.set_ylabel("人口増減率×着工率 の相関係数")
    ax.set_title("人口密度区分別の相関: 延床面積ベースだけが都市→地方で単調に弱まる")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig1_density_correlation.png", dpi=150)
    plt.close(fig)


def fig2_scatter_by_density():
    """密度区分ごとの 人口増減率×延床面積ベース着工率 の散布図（回帰直線つき）。"""
    df = pd.read_csv(PROCESSED_DIR / "analysis1b_size_segments.csv")

    fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True, sharey=True)
    for ax, group, label in zip(axes.flat, DENSITY_ORDER, DENSITY_LABELS):
        sub = df[df["size_group"] == group]
        ax.scatter(sub["pop_change_00_20"], sub["housing_floor_rate"], s=10, alpha=0.4, color="#2563eb")
        if len(sub) > 2:
            coef = np.polyfit(sub["pop_change_00_20"], sub["housing_floor_rate"], 1)
            xs = np.linspace(sub["pop_change_00_20"].min(), sub["pop_change_00_20"].max(), 50)
            ax.plot(xs, np.polyval(coef, xs), color="#dc2626", linewidth=1.5)
        ax.set_title(label.replace("\n", " "), fontsize=10)
        ax.axvline(0, color="gray", linewidth=0.5)
    fig.supxlabel("人口増減率 2000→2020 (%)")
    fig.supylabel("延床面積ベース着工率 (m2/世帯, 2011-2023)")
    fig.suptitle("密度区分別: 人口増減率 と 住宅着工の関係")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig2_scatter_by_density.png", dpi=150)
    plt.close(fig)


def fig3_owned_ratio_by_density():
    """密度区分別の持ち家率（案1-f0）。「地方ほど持ち家率が高い」を示す。"""
    df = pd.read_csv(PROCESSED_DIR / "analysis1f0_density_owned_ratio.csv", index_col=0)
    df = df.loc[DENSITY_ORDER]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(DENSITY_LABELS, df["mean"] * 100, color="#16a34a")
    for i, v in enumerate(df["mean"] * 100):
        ax.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=10)
    ax.set_ylabel("持ち家率 (%)")
    ax.set_ylim(0, 100)
    ax.set_title("人口密度区分別の持ち家率: 地方ほど「戸建て信仰」が強い")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_owned_ratio_by_density.png", dpi=150)
    plt.close(fig)


def fig4_model_comparison():
    """統合モデルのネスト比較（案1-i）: 各変数を足すごとにR^2がどれだけ改善するか。"""
    df = pd.read_csv(PROCESSED_DIR / "analysis1i_model_comparison.csv")
    labels = ["M0\n密度のみ", "M1\n+持ち家率", "M2\n+通勤時間", "M3\n+地価"]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(labels, df["adj_r2"], color=["#94a3b8", "#2563eb", "#2563eb", "#94a3b8"])
    for i, v in enumerate(df["adj_r2"]):
        ax.text(i, v + 0.003, f"{v:.3f}", ha="center", fontsize=10)
    ax.set_ylabel("調整済みR^2")
    ax.set_title("統合モデルのネスト比較: 持ち家率・通勤時間は追加の説明力あり、地価はわずか")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig4_model_comparison.png", dpi=150)
    plt.close(fig)


def fig5_moderator_robustness():
    """持ち家率 vs 通勤時間の交互作用項について、生DVと対数DVでのp値を比較（案1-i）。
    持ち家率は両方で有意、通勤時間は対数DVで非有意になる、という頑健性の違いを示す。
    """
    df = pd.read_csv(PROCESSED_DIR / "analysis1i_moderator_robustness.csv")
    labels = df["moderator"].tolist()
    p_raw = df["p_raw_dv"].tolist()
    p_log = df["p_log_dv"].tolist()

    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = np.arange(len(labels))
    w = 0.35
    ax.bar(x - w / 2, p_raw, w, label="生DV (housing_floor_rate)", color="#94a3b8")
    ax.bar(x + w / 2, p_log, w, label="対数DV (log housing_floor_rate)", color="#2563eb")
    ax.axhline(0.05, color="#dc2626", linewidth=1, linestyle="--", label="有意水準 p=0.05")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("交互作用項の p値")
    ax.set_title("頑健性確認: 持ち家率は対数変換後も有意、通勤時間は非有意化")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig5_moderator_robustness.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig1_density_correlation()
    fig2_scatter_by_density()
    fig3_owned_ratio_by_density()
    fig4_model_comparison()
    fig5_moderator_robustness()
    print(f"saved figures to {FIG_DIR}")
