"""3つの分析を実行し、市区町村単位の集計結果を data/processed/ に保存する。

案1: 人口減少率(2000→2020) × 住宅着工率(2011-2023合計/2020年世帯数) の相関・外れ値
案1-b: 案1を人口密度（2020年人口/面積、高密度都市部/都市部/郊外・地方都市/農山村・過疎的の4区分）で分割した相関
案1-c: 案1-bの r（棟数） と rho（Spearman）の食い違いが外れ値のせいかを、ウィンザライズして確認
案1-d: 「相関が密度区分で強弱するのは地価水準の違いで説明できるか」を交互作用項付き回帰で検証
案1-e: 案1-bと直接比較するため、密度の代わりに地価四分位で区分した場合の相関
案1-f0: 前提確認（地方ほど持ち家率が高いか）: log(人口密度) × 持ち家率 の相関・密度区分別の持ち家率
案1-f: 案1-dと同じ枠組みで、持ち家率（地方の「戸建て信仰」）が相関の強弱を説明できるかを検証
案1-g: 案1-bと直接比較するため、密度の代わりに持ち家率四分位で区分した場合の相関
案2: 世帯分裂パラドックス（人口は減っているが世帯数は増えている自治体）と住宅着工の関係
案3: 地価水準 × 住宅着工率 × 人口減少率 による自治体クラスタリング（KMeans）

使い方:
    python scripts/analyze.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def load_panel() -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "merged_panel.csv")


def build_base_table(panel: pd.DataFrame) -> pd.DataFrame:
    """市区町村コードを行、年次指標を列にした集計テーブルを作る。"""
    names = panel.dropna(subset=["area_name"]).drop_duplicates("area_code").set_index("area_code")["area_name"]

    pop = panel.pivot_table(index="area_code", columns="year", values="population")
    pop.columns = [f"pop_{int(y)}" for y in pop.columns]

    hh = panel.pivot_table(index="area_code", columns="year", values="households")
    hh.columns = [f"hh_{int(y)}" for y in hh.columns]

    area_km2 = panel.pivot_table(index="area_code", columns="year", values="area_km2")
    area_km2.columns = [f"area_km2_{int(y)}" for y in area_km2.columns]

    housing_total = (
        panel.groupby("area_code")["housing_starts_count"].sum(min_count=1).rename("housing_starts_total_11_23")
    )
    housing_floor_total = (
        panel.groupby("area_code")["housing_floor_area_m2"].sum(min_count=1).rename("housing_floor_total_11_23")
    )
    housing_years = (
        panel.dropna(subset=["housing_starts_count"]).groupby("area_code")["year"].nunique().rename("housing_years_n")
    )

    land = (
        panel.groupby("area_code")["land_price_mean_per_sqm"].mean().rename("land_price_avg_22_26")
    )
    land_n = (
        panel.groupby("area_code")["land_price_n_points"].sum(min_count=1).rename("land_price_points_total")
    )

    # 持ち家/借家比率（2023年単年、年次を持たないため merged_panel には含まれない別ファイルから結合）
    tenure = pd.read_csv(PROCESSED_DIR / "housing_tenure.csv").set_index("area_code")
    owned_ratio = tenure["owned_ratio"].rename("owned_ratio")
    rented_private_ratio = tenure["rented_private_ratio"].rename("rented_private_ratio")

    base = pd.concat(
        [pop, hh, area_km2, housing_total, housing_floor_total, housing_years, land, land_n,
         owned_ratio, rented_private_ratio],
        axis=1,
    )
    base["area_name"] = names
    base = base.reset_index()
    return base


# ---------- 案1: 人口減少 × 住宅着工 ----------

def analysis1_pop_vs_housing(base: pd.DataFrame) -> pd.DataFrame:
    df = base.dropna(subset=["pop_2000", "pop_2020", "hh_2020", "housing_starts_total_11_23",
                              "housing_floor_total_11_23"]).copy()
    df = df[(df["pop_2000"] > 0) & (df["hh_2020"] > 0)]

    df["pop_change_00_20"] = (df["pop_2020"] - df["pop_2000"]) / df["pop_2000"] * 100
    df["housing_starts_rate"] = df["housing_starts_total_11_23"] / df["hh_2020"] * 1000
    # 棟数（housing_starts_rate）は集合住宅1棟＝1件と数えるため、高密度都市部でのタワマン等の
    # 大規模供給を過小評価する。世帯あたり延床面積(m2)ベースの指標も併せて持たせておく
    # （案1-bの人口密度区分別分析で、指標選択がどれだけ結論を左右するかを示すのに使う）。
    df["housing_floor_rate"] = df["housing_floor_total_11_23"] / df["hh_2020"]

    r, p = stats.pearsonr(df["pop_change_00_20"], df["housing_starts_rate"])
    rho, p_rho = stats.spearmanr(df["pop_change_00_20"], df["housing_starts_rate"])
    print(f"[案1] n={len(df)}  Pearson r={r:.3f} (p={p:.2e})  Spearman rho={rho:.3f} (p={p_rho:.2e})")

    q_pop_low = df["pop_change_00_20"].quantile(0.25)
    q_rate_high = df["housing_starts_rate"].quantile(0.75)
    df["oversupply_flag"] = (df["pop_change_00_20"] <= q_pop_low) & (df["housing_starts_rate"] >= q_rate_high)
    print(f"[案1] 人口減少率下位25% かつ 着工率上位25% の自治体（供給過剰の疑い）: {df['oversupply_flag'].sum()}件")

    # 2011年東日本大震災の被災・避難指示対象地域は、住宅着工が「災害公営住宅の建設」という
    # 特殊要因で跳ね上がるため、通常の需給ギャップとは性質が異なる。人口が50%以上減少した
    # 自治体を目印として別途フラグを立てる（正確な被災地域リストではなく、経済的な供給過剰との
    # 混同を避けるための粗いフラグ）。
    df["extreme_decline_flag"] = df["pop_change_00_20"] <= -50

    # 逆に+100%を超える人口増は、平成の大合併（2005年前後）で周辺町村を編入した結果、同じ
    # area_code のまま実質的な行政区域が拡大したケースが大半（例: 日光市, 越前町, 永平寺町）。
    # ただし東京都中央区のような正真正銘の人口回帰（都心のタワーマンション開発等）も含まれるため、
    # 「合併の可能性が高い」という粗いフラグに留め、断定はしない。
    df["extreme_growth_flag"] = df["pop_change_00_20"] >= 100

    out_cols = ["area_code", "area_name", "pop_2000", "pop_2020", "pop_change_00_20",
                "hh_2020", "housing_starts_total_11_23", "housing_starts_rate", "housing_floor_rate",
                "oversupply_flag", "extreme_decline_flag", "extreme_growth_flag"]
    result = df[out_cols].sort_values("pop_change_00_20")
    result.to_csv(PROCESSED_DIR / "analysis1_pop_housing.csv", index=False)

    top_oversupply = result[result.oversupply_flag].sort_values("housing_starts_rate", ascending=False).head(10)
    print("[案1] 供給過剰候補 上位10:")
    print(top_oversupply[["area_name", "pop_change_00_20", "housing_starts_rate"]].to_string(index=False))
    return result


# 人口だけで「規模」を測ると、平成の大合併で山間部まで編入した広域・低密度な自治体
# （例: 石川県白山市、人口11万人だが面積755km2・密度146人/km2）が、渋谷区のような高密度都心と
# 同じ「大規模」区分に入ってしまう。人口集中地区(DID)の閾値として知られる4,000人/km2を軸に、
# 人口密度（2020年人口／2020年面積）で区分し直す。
DENSITY_BINS = [
    (4_000, float("inf"), "1_高密度都市部(4000人/km2以上)"),
    (1_000, 4_000, "2_都市部(1000-4000人/km2)"),
    (300, 1_000, "3_郊外・地方都市(300-1000人/km2)"),
    (0, 300, "4_農山村・過疎的(300人/km2未満)"),
]


def _density_group(density: float) -> str:
    for lo, hi, label in DENSITY_BINS:
        if lo <= density < hi:
            return label
    return DENSITY_BINS[-1][2]


def analysis1b_size_segmented(result1: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """案1を自治体の人口密度（2020年人口／2020年面積）で4分割し、区分別に相関を見る。

    震災・合併による極端値（extreme_decline_flag / extreme_growth_flag）は前回の分析で
    相関を歪めることが分かっているため除外したサンプルで計算する。
    """
    clean = result1[~result1["extreme_decline_flag"] & ~result1["extreme_growth_flag"]].copy()
    clean = clean.merge(base[["area_code", "area_km2_2020"]], on="area_code", how="left")
    clean = clean.dropna(subset=["area_km2_2020"])
    clean = clean[clean["area_km2_2020"] > 0]
    clean["density_2020"] = clean["pop_2020"] / clean["area_km2_2020"]
    clean["size_group"] = clean["density_2020"].apply(_density_group)

    rows = []
    for g, sub in clean.groupby("size_group"):
        r, p = stats.pearsonr(sub["pop_change_00_20"], sub["housing_starts_rate"])
        rho, p_rho = stats.spearmanr(sub["pop_change_00_20"], sub["housing_starts_rate"])
        # 棟数ベースは集合住宅の多い高密度都市部で供給を過小評価するため、延床面積ベースの
        # 相関も並べて出す（この2つがどれだけ乖離するかが指標選択の影響を物語る）。
        r_floor, p_floor = stats.pearsonr(sub["pop_change_00_20"], sub["housing_floor_rate"])
        rows.append({
            "size_group": g, "n": len(sub),
            "pop_change_mean": sub["pop_change_00_20"].mean(),
            "housing_rate_mean": sub["housing_starts_rate"].mean(),
            "density_mean": sub["density_2020"].mean(),
            "pearson_r": r, "pearson_p": p, "spearman_rho": rho, "spearman_p": p_rho,
            "pearson_r_floor": r_floor, "pearson_p_floor": p_floor,
        })
    summary = pd.DataFrame(rows).sort_values("size_group")
    print("[案1-b] 人口密度区分別の 人口増減率×着工率 相関（棟数ベース r と 延床面積ベース r_floor の比較）:")
    print(summary.to_string(index=False))

    clean.to_csv(PROCESSED_DIR / "analysis1b_size_segments.csv", index=False)
    summary.to_csv(PROCESSED_DIR / "analysis1b_size_summary.csv", index=False)
    return clean, summary


# ---------- 案1-c: r と rho の食い違いは外れ値のせいか ----------

def _winsorized_pearson(sub: pd.DataFrame, x_col: str, y_col: str, lo: float = 0.01, hi: float = 0.99):
    x = sub[x_col].clip(sub[x_col].quantile(lo), sub[x_col].quantile(hi))
    y = sub[y_col].clip(sub[y_col].quantile(lo), sub[y_col].quantile(hi))
    return stats.pearsonr(x, y)


def analysis1c_metric_robustness(clean: pd.DataFrame) -> pd.DataFrame:
    """案1-bで、棟数ベースのPearson r（例: 高密度都市部で-0.30）とSpearman rho（同 -0.20）は
    符号こそ揃うが、延床面積ベースのr_floor（同 0.70、単調減少）とは傾向が食い違っていた。
    区分内で1/99パーセンタイルにウィンザライズしたPearson rと比較し、少数の外れ値が
    棟数ベース指標を歪めているだけなのか、それとも指標の性質（集合住宅の数え方）自体による
    本質的な食い違いなのかを切り分ける。
    """
    rows = []
    for g, sub in clean.groupby("size_group"):
        r_raw, _ = stats.pearsonr(sub["pop_change_00_20"], sub["housing_starts_rate"])
        r_floor_raw, _ = stats.pearsonr(sub["pop_change_00_20"], sub["housing_floor_rate"])
        rho_raw, _ = stats.spearmanr(sub["pop_change_00_20"], sub["housing_starts_rate"])
        rho_floor_raw, _ = stats.spearmanr(sub["pop_change_00_20"], sub["housing_floor_rate"])

        r_win, _ = _winsorized_pearson(sub, "pop_change_00_20", "housing_starts_rate")
        r_floor_win, _ = _winsorized_pearson(sub, "pop_change_00_20", "housing_floor_rate")

        rows.append({
            "size_group": g, "n": len(sub),
            "r_raw": r_raw, "r_winsorized": r_win,
            "r_floor_raw": r_floor_raw, "r_floor_winsorized": r_floor_win,
            "spearman_rho": rho_raw, "spearman_rho_floor": rho_floor_raw,
        })
    out = pd.DataFrame(rows).sort_values("size_group")
    print("[案1-c] 指標・外れ値ロバストネス（生値 vs 1/99%ウィンザライズ後のPearson r）:")
    print(out.to_string(index=False))
    out.to_csv(PROCESSED_DIR / "analysis1c_metric_robustness.csv", index=False)
    return out


# ---------- 案1-d: 相関の強弱は地価水準で説明できるか（交互作用モデル） ----------

def analysis1d_land_price_moderation(clean: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """人口密度区分ごとに r_floor が 0.70→0.60→0.48→0.36 と単調減少していたのが、
    地価水準の違いで説明できる（＝地価をモデルに入れれば密度区分による差が消える）のかを、
    人口変化率 × log(地価) の交互作用項を持つOLS回帰で検証する。

    交互作用項の係数が正で有意なら「地価が高いほど人口変化が着工率に与える影響が強い」
    ＝地価が相関の強弱を（少なくとも部分的に）説明している、と解釈できる。
    log(人口密度) を統制変数として入れ、密度そのものの効果と地価の効果を分離する。
    """
    df = clean.merge(base[["area_code", "land_price_avg_22_26"]], on="area_code", how="left")
    df = df.dropna(subset=["land_price_avg_22_26"])
    df = df[df["land_price_avg_22_26"] > 0]
    df["log_land_price"] = np.log10(df["land_price_avg_22_26"])
    df["log_density"] = np.log10(df["density_2020"])

    print(f"[案1-d] n={len(df)}（地価データありの自治体のみ）")

    m_density_only = smf.ols("housing_floor_rate ~ pop_change_00_20 * log_density", data=df).fit()
    m_full = smf.ols(
        "housing_floor_rate ~ pop_change_00_20 * log_land_price + log_density",
        data=df,
    ).fit()

    print("\n[案1-d] 比較用: 密度のみとの交互作用モデル")
    print(f"  pop_change_00_20:log_density = {m_density_only.params['pop_change_00_20:log_density']:.4f} "
          f"(p={m_density_only.pvalues['pop_change_00_20:log_density']:.2e})")

    print("\n[案1-d] 本命: 地価 × 人口変化の交互作用モデル（log_density統制）")
    print(m_full.summary())

    interaction_coef = m_full.params["pop_change_00_20:log_land_price"]
    interaction_p = m_full.pvalues["pop_change_00_20:log_land_price"]
    print(f"\n[案1-d] 交互作用項 pop_change_00_20:log_land_price = {interaction_coef:.4f} (p={interaction_p:.2e})")
    if interaction_p < 0.05:
        direction = "地価が高いほど人口変化が着工率に与える影響が強い" if interaction_coef > 0 \
            else "地価が高いほど人口変化が着工率に与える影響が弱い"
        print(f"[案1-d] → 統計的に有意（log_density統制後も残る）。{direction}。地価は密度と別に相関の強弱を説明する。")
    else:
        print("[案1-d] → log_density統制後は交互作用が有意でない"
              "（＝地価の効果は密度と重複しており、独立の説明力は乏しい可能性）")

    with open(PROCESSED_DIR / "analysis1d_land_price_moderation.txt", "w") as f:
        f.write("=== 密度のみとの交互作用モデル ===\n")
        f.write(m_density_only.summary().as_text())
        f.write("\n\n=== 地価 × 人口変化（log_density統制） ===\n")
        f.write(m_full.summary().as_text())

    return df


# ---------- 案1-e: 密度区分の代わりに地価四分位で区分した場合の相関 ----------

def analysis1e_land_price_segmented(clean: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """案1-bの密度区分テーブルと直接比較できるよう、同じ変数・同じサンプルを
    地価（2022-2026平均）の四分位で区分し直して相関を計算する。
    密度区分での傾向（r_floor単調減少）が、地価区分でも同様に見られるかを確認する。
    """
    df = clean.merge(base[["area_code", "land_price_avg_22_26"]], on="area_code", how="left")
    df = df.dropna(subset=["land_price_avg_22_26"])
    df = df[df["land_price_avg_22_26"] > 0]

    df["land_price_quartile"] = pd.qcut(
        df["land_price_avg_22_26"], 4,
        labels=["1_Q1(最安)", "2_Q2", "3_Q3", "4_Q4(最高)"],
    )

    rows = []
    for g, sub in df.groupby("land_price_quartile", observed=True):
        r, p = stats.pearsonr(sub["pop_change_00_20"], sub["housing_starts_rate"])
        r_floor, p_floor = stats.pearsonr(sub["pop_change_00_20"], sub["housing_floor_rate"])
        rho, p_rho = stats.spearmanr(sub["pop_change_00_20"], sub["housing_starts_rate"])
        rows.append({
            "land_price_quartile": g, "n": len(sub),
            "land_price_mean": sub["land_price_avg_22_26"].mean(),
            "pearson_r": r, "pearson_r_floor": r_floor, "spearman_rho": rho,
        })
    summary = pd.DataFrame(rows).sort_values("land_price_quartile")
    print("[案1-e] 地価四分位区分別の 人口増減率×着工率 相関（案1-bの密度区分と比較用）:")
    print(summary.to_string(index=False))
    df.to_csv(PROCESSED_DIR / "analysis1e_land_price_segments.csv", index=False)
    summary.to_csv(PROCESSED_DIR / "analysis1e_land_price_summary.csv", index=False)
    return summary


def analysis1f0_density_vs_owned_ratio(clean: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """案1-fの前提（「地方ほど持ち家率が高い」）を裏付けるため、
    人口密度区分別の持ち家率と、log(密度) × 持ち家率 の相関を確認する。
    """
    df = clean.merge(base[["area_code", "owned_ratio"]], on="area_code", how="left")
    df = df.dropna(subset=["owned_ratio"])
    df["log_density"] = np.log10(df["density_2020"])

    r, p = stats.pearsonr(df["log_density"], df["owned_ratio"])
    print(f"[案1-f0] log(人口密度) と 持ち家率 の相関: r={r:.3f} (p={p:.2e}, n={len(df)})")

    summary = df.groupby("size_group")["owned_ratio"].agg(["mean", "median", "count"]).sort_index()
    print("[案1-f0] 密度区分別の持ち家率（地方ほど持ち家率が高い、という前提の確認）:")
    print(summary.to_string())
    summary.to_csv(PROCESSED_DIR / "analysis1f0_density_owned_ratio.csv")
    return df


# ---------- 案1-f: 相関の強弱は持ち家率で説明できるか（交互作用モデル） ----------

def analysis1f_tenure_moderation(clean: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """地方は「戸建て信仰」が強く持ち家率が高いため、住宅着工が人口動態と連動しにくい
    （持ち家取得はライフイベント的な動機で、賃貸市場のような需給調整が働きにくい）という仮説を、
    案1-dと同じ交互作用回帰の枠組みで検証する。2023年住宅・土地統計調査の持ち家率
    （2区分: 持ち家/借家）を使用。地価（案1-d）との比較のため同じモデル構造にする。

    前段として案1-f0で「地方ほど持ち家率が高い」（log密度と持ち家率の相関 r=-0.64）こと自体を
    確認しており、本関数はその上で「持ち家率が人口変化→着工率の効果を弱めるか」を検証する。
    """
    analysis1f0_density_vs_owned_ratio(clean, base)

    df = clean.merge(base[["area_code", "owned_ratio"]], on="area_code", how="left")
    df = df.dropna(subset=["owned_ratio"])
    df["log_density"] = np.log10(df["density_2020"])

    print(f"[案1-f] n={len(df)}（持ち家率データありの自治体のみ）")

    m_full = smf.ols(
        "housing_floor_rate ~ pop_change_00_20 * owned_ratio + log_density",
        data=df,
    ).fit()
    print("\n[案1-f] 持ち家率 × 人口変化の交互作用モデル（log_density統制）")
    print(m_full.summary())

    interaction_coef = m_full.params["pop_change_00_20:owned_ratio"]
    interaction_p = m_full.pvalues["pop_change_00_20:owned_ratio"]
    print(f"\n[案1-f] 交互作用項 pop_change_00_20:owned_ratio = {interaction_coef:.4f} (p={interaction_p:.2e})")
    if interaction_p < 0.05:
        direction = "持ち家率が高いほど人口変化が着工率に与える影響が強い" if interaction_coef > 0 \
            else "持ち家率が高いほど人口変化が着工率に与える影響が弱い"
        print(f"[案1-f] → 統計的に有意（log_density統制後も残る）。{direction}。"
              "地価（案1-dはp=0.069で非有意）より明確に、密度区分の相関の強弱を説明する。")
    else:
        print("[案1-f] → log_density統制後は交互作用が有意でない")

    with open(PROCESSED_DIR / "analysis1f_tenure_moderation.txt", "w") as f:
        f.write(m_full.summary().as_text())

    return df


# ---------- 案1-g: 密度区分の代わりに持ち家率四分位で区分した場合の相関 ----------

def analysis1g_tenure_segmented(clean: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """案1-b/1-eと直接比較できるよう、持ち家率の四分位で区分し直して相関を計算する。"""
    df = clean.merge(base[["area_code", "owned_ratio"]], on="area_code", how="left")
    df = df.dropna(subset=["owned_ratio"])

    df["owned_ratio_quartile"] = pd.qcut(
        df["owned_ratio"], 4,
        labels=["1_Q1(持ち家率最低)", "2_Q2", "3_Q3", "4_Q4(持ち家率最高)"],
    )

    rows = []
    for g, sub in df.groupby("owned_ratio_quartile", observed=True):
        r, p = stats.pearsonr(sub["pop_change_00_20"], sub["housing_starts_rate"])
        r_floor, p_floor = stats.pearsonr(sub["pop_change_00_20"], sub["housing_floor_rate"])
        rho, p_rho = stats.spearmanr(sub["pop_change_00_20"], sub["housing_starts_rate"])
        rows.append({
            "owned_ratio_quartile": g, "n": len(sub),
            "owned_ratio_mean": sub["owned_ratio"].mean(),
            "pearson_r": r, "pearson_r_floor": r_floor, "spearman_rho": rho,
        })
    summary = pd.DataFrame(rows).sort_values("owned_ratio_quartile")
    print("[案1-g] 持ち家率四分位区分別の 人口増減率×着工率 相関（案1-bの密度区分と比較用）:")
    print(summary.to_string(index=False))
    df.to_csv(PROCESSED_DIR / "analysis1g_tenure_segments.csv", index=False)
    summary.to_csv(PROCESSED_DIR / "analysis1g_tenure_summary.csv", index=False)
    return summary


# ---------- 案2: 世帯分裂パラドックス ----------

def analysis2_household_divergence(base: pd.DataFrame) -> pd.DataFrame:
    df = base.dropna(subset=["pop_2000", "pop_2020", "hh_2000", "hh_2020", "housing_starts_total_11_23"]).copy()
    df = df[(df["pop_2000"] > 0) & (df["hh_2000"] > 0)]

    df["pop_change_00_20"] = (df["pop_2020"] - df["pop_2000"]) / df["pop_2000"] * 100
    df["hh_change_00_20"] = (df["hh_2020"] - df["hh_2000"]) / df["hh_2000"] * 100
    df["divergence"] = df["hh_change_00_20"] - df["pop_change_00_20"]
    df["housing_starts_rate"] = df["housing_starts_total_11_23"] / df["hh_2020"] * 1000

    paradox = df[(df["pop_change_00_20"] < 0) & (df["hh_change_00_20"] > 0)]
    print(f"[案2] n={len(df)}  人口減少×世帯数増加（パラドックス自治体）: {len(paradox)}件 "
          f"({len(paradox) / len(df) * 100:.1f}%)")

    valid = df.dropna(subset=["housing_starts_rate"])
    r, p = stats.pearsonr(valid["divergence"], valid["housing_starts_rate"])
    print(f"[案2] 乖離幅(divergence) と 着工率 の相関: r={r:.3f} (p={p:.2e})")

    df["paradox_flag"] = (df["pop_change_00_20"] < 0) & (df["hh_change_00_20"] > 0)
    # 案1と同じ理由（震災の避難指示・平成の大合併）で極端値に注意が必要（例: 福島県広野町）。
    df["extreme_decline_flag"] = df["pop_change_00_20"] <= -50
    df["extreme_growth_flag"] = df["pop_change_00_20"] >= 100

    out_cols = ["area_code", "area_name", "pop_change_00_20", "hh_change_00_20",
                "divergence", "housing_starts_rate", "paradox_flag",
                "extreme_decline_flag", "extreme_growth_flag"]
    result = df[out_cols].sort_values("divergence", ascending=False)
    result.to_csv(PROCESSED_DIR / "analysis2_household_divergence.csv", index=False)

    print("[案2] 乖離幅 上位10（人口減少が最も激しいのに世帯数が増えている自治体）:")
    top = paradox.sort_values("divergence", ascending=False).head(10)
    print(top[["area_name", "pop_change_00_20", "hh_change_00_20", "divergence"]].to_string(index=False))
    return result


# ---------- 案3: クラスタリング ----------

def analysis3_clustering(base: pd.DataFrame, n_clusters: int = 4) -> pd.DataFrame:
    df = base.dropna(subset=["pop_2015", "pop_2020", "hh_2020", "housing_starts_total_11_23",
                              "land_price_avg_22_26"]).copy()
    df = df[(df["pop_2015"] > 0) & (df["hh_2020"] > 0) & (df["land_price_avg_22_26"] > 0)]

    df["pop_change_15_20"] = (df["pop_2020"] - df["pop_2015"]) / df["pop_2015"] * 100
    df["housing_starts_rate"] = df["housing_starts_total_11_23"] / df["hh_2020"] * 1000
    df["log_land_price"] = np.log10(df["land_price_avg_22_26"])

    features = ["pop_change_15_20", "housing_starts_rate", "log_land_price"]
    # 2011年東日本大震災の避難指示解除に伴う急激な人口回帰（例: 楢葉町 +279%）など、単一の
    # 極端値がKMeansの重心を引きずってしまうため、クラスタリング用の特徴量だけ1/99パーセンタイルで
    # ウィンザライズする（出力する pop_change_15_20 自体は生値のまま残す）。
    clip_bounds = {f: (df[f].quantile(0.01), df[f].quantile(0.99)) for f in features}
    X_df = df[features].copy()
    for f, (lo, hi) in clip_bounds.items():
        X_df[f] = X_df[f].clip(lo, hi)
    df["extreme_change_flag"] = (df["pop_change_15_20"] < clip_bounds["pop_change_15_20"][0]) | \
                                 (df["pop_change_15_20"] > clip_bounds["pop_change_15_20"][1])

    X = StandardScaler().fit_transform(X_df)

    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=0)
    df["cluster"] = km.fit_predict(X)

    print(f"[案3] n={len(df)}  クラスタ数={n_clusters}")
    summary = df.groupby("cluster")[["pop_change_15_20", "housing_starts_rate", "land_price_avg_22_26"]].agg(
        ["mean", "count"]
    )
    print(summary)

    yubari = df[df["area_name"].str.contains("夕張", na=False)]
    if not yubari.empty:
        print("[案3] 夕張市の所属クラスタ:")
        print(yubari[["area_name", "pop_change_15_20", "housing_starts_rate",
                       "land_price_avg_22_26", "cluster"]].to_string(index=False))

    out_cols = ["area_code", "area_name", "pop_change_15_20", "housing_starts_rate",
                "land_price_avg_22_26", "log_land_price", "cluster", "extreme_change_flag"]
    result = df[out_cols].sort_values("cluster")
    result.to_csv(PROCESSED_DIR / "analysis3_clusters.csv", index=False)
    return result


if __name__ == "__main__":
    panel = load_panel()
    base = build_base_table(panel)
    base.to_csv(PROCESSED_DIR / "base_table.csv", index=False)

    print("=" * 60)
    result1 = analysis1_pop_vs_housing(base)
    print("=" * 60)
    clean1b, _ = analysis1b_size_segmented(result1, base)
    print("=" * 60)
    analysis1c_metric_robustness(clean1b)
    print("=" * 60)
    analysis1d_land_price_moderation(clean1b, base)
    print("=" * 60)
    analysis1e_land_price_segmented(clean1b, base)
    print("=" * 60)
    analysis1f_tenure_moderation(clean1b, base)
    print("=" * 60)
    analysis1g_tenure_segmented(clean1b, base)
    print("=" * 60)
    analysis2_household_divergence(base)
    print("=" * 60)
    analysis3_clustering(base)
