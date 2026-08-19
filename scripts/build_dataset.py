"""国勢調査（人口・世帯数）・住宅着工件数・公示地価・持ち家/借家比率・通勤時間を市区町村コード単位で統合する。

各データソースの市区町村コード体系は、テーブルごとに @level の振り方が異なる（政令指定都市の
「市全体」行を level3 で表す年もあれば level4 で表す年もある）。そのため level 番号ではなく、
「他のどのコードの parentCode にもなっていない」leaf ノードを市区町村単位とみなして抽出する
（全国・都道府県・政令指定都市の合算行を自動的に除外できる）。

出力（data/processed/）:
    population_households.csv  年 × 市区町村コード：人口・世帯数（2000, 2005, 2010, 2015, 2020）
    housing_starts.csv          年 × 市区町村コード：住宅系着工件数・床面積・工事費予定額
                                 （2011〜2023、暦年/年度の切り替わりに period_type で印を付ける）
    land_price.csv               年 × 市区町村コード：公示地価（住宅地）の平均・中央値・地点数
                                 （2022〜2026）
    housing_tenure.csv            市区町村コード：持ち家/借家（内訳: 公営/UR・公社/民営/給与）
                                 の住宅数・持ち家率（2023年単年の横断データ、年次を持たない）
    commute.csv                   市区町村コード：通勤時間中位数（分、都市圏アクセスの代理指標。
                                 2023年単年の横断データ、年次を持たない）
    merged_panel.csv             population_households/housing_starts/land_price の3つを
                                 year, area_code で外部結合したロング形式パネル
                                 （housing_tenure・commute は年次を持たないためこのパネルには
                                 含めず、分析側で area_code のみで別途結合する）

使い方:
    python scripts/build_dataset.py
"""
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

RESIDENTIAL_CAT01 = {"12", "13", "14"}  # 居住専用住宅, 居住専用準住宅, 居住産業併用建築物
HOUSING_TAB_METRICS = {"12": "housing_starts_count", "13": "housing_floor_area_m2", "14": "housing_cost_10k_yen"}

# 住宅の所有の関係（cat02）: 1=持ち家, 2=借家計, 21=公営, 22=UR・公社, 23=民営, 24=給与住宅
TENURE_CAT02_METRICS = {
    "1": "owned", "2": "rented_total",
    "21": "rented_public", "22": "rented_ur_kosha", "23": "rented_private", "24": "rented_company",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _to_num(s: str) -> float | None:
    """e-Stat の秘匿・非該当プレースホルダー（"-", "X", "*" 等）を NaN 相当の None に変換する。"""
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _leaf_area_codes(class_obj: list) -> dict:
    """area の CLASS_OBJ から {市区町村コード: 名称} を返す（全国・都道府県・政令市合算行は除外）。

    2010年・2015年の表には、市町村合併の前後比較用に「(旧 ○○市)」という旧市区町村の参考行や、
    「○○郡」「○○県市部/郡部」「全国市部/郡部」（郡・都市/郡部単位の集計行）、北海道の
    「○○振興局/支庁」（広域行政区分の集計行）が、実際の市区町村と同じ parentCode（都道府県）に
    フラットに同居しており、それらの子であるべき市区町村の parentCode にはなっていない。
    leaf 判定（他のどのコードの parentCode にもなっていない）だけでは除外できないため、
    これらの集計行を名称パターンで別途除外する。

    さらに、住宅・土地統計調査系の表（例: 0004021424）では「全国」(00000)が「北海道」等の
    都道府県行と同じ @level=1 でフラットに並び、都道府県側にも @parentCode="00000" が
    振られていない。そのため 00000 がどの行の parentCode にもならず leaf 判定をすり抜けて
    しまう。コードを直接見て除外する。
    """
    area_cls = next(c["CLASS"] for c in class_obj if c["@id"] == "area")
    if isinstance(area_cls, dict):
        area_cls = [area_cls]
    parents = {c.get("@parentCode") for c in area_cls if c.get("@parentCode")}

    def _is_aggregate_row(code: str, name: str) -> bool:
        if code == "00000":
            return True
        if "旧" in name:
            return True
        if name.endswith(("郡", "市部", "郡部", "振興局", "支庁")):
            return True
        return False

    return {
        c["@code"]: c["@name"] for c in area_cls
        if c["@code"] not in parents and not _is_aggregate_row(c["@code"], c["@name"])
    }


# ---------- 1. 国勢調査：人口・世帯数 ----------

def load_census() -> pd.DataFrame:
    rows = []

    # 2000, 2005, 2010: cat01 コード方式（100=人口総数, 260=世帯数）
    cat01_files = {
        2000: "census_2000_0003391075.json",
        2005: "census_2005_0003408216.json",
        2010: "census_2010_0003411171.json",
    }
    for year, fname in cat01_files.items():
        stat = _load_json(RAW_DIR / fname)["GET_STATS_DATA"]["STATISTICAL_DATA"]
        leaf = _leaf_area_codes(stat["CLASS_INF"]["CLASS_OBJ"])
        pop, hh, area = {}, {}, {}
        for v in stat["DATA_INF"]["VALUE"]:
            code = v["@area"]
            if code not in leaf:
                continue
            if v["@cat01"] == "100":
                pop[code] = _to_num(v["$"])
            elif v["@cat01"] == "260":
                hh[code] = _to_num(v["$"])
            elif v["@cat01"] == "140":
                area[code] = _to_num(v["$"])
        for code in set(pop) | set(hh):
            rows.append({"year": year, "area_code": code, "area_name": leaf[code],
                         "population": pop.get(code), "households": hh.get(code),
                         "area_km2": area.get(code)})

    # 2015: tab コード方式（020=人口, 109=世帯数）。この表には cat01（全域・人口集中地区の内訳、
    # 00710=全域, 00711以降=人口集中地区の細分）がもう1軸あり、指定しないと同一 tab/area に対して
    # 複数のcat01の値が存在し、後勝ちで人口集中地区の一部だけの数値に上書きされてしまう。
    # 全域の合計値である cat01=00710 のみを使う。
    stat = _load_json(RAW_DIR / "census_2015_0003148500.json")["GET_STATS_DATA"]["STATISTICAL_DATA"]
    leaf = _leaf_area_codes(stat["CLASS_INF"]["CLASS_OBJ"])
    pop, hh, area = {}, {}, {}
    for v in stat["DATA_INF"]["VALUE"]:
        code = v["@area"]
        if code not in leaf or v.get("@cat01") != "00710":
            continue
        if v["@tab"] == "020":
            pop[code] = _to_num(v["$"])
        elif v["@tab"] == "109":
            hh[code] = _to_num(v["$"])
        elif v["@tab"] == "103":
            area[code] = _to_num(v["$"])
    for code in set(pop) | set(hh):
        rows.append({"year": 2015, "area_code": code, "area_name": leaf[code],
                     "population": pop.get(code), "households": hh.get(code),
                     "area_km2": area.get(code)})

    # 2020: 現数値人口は別表 0003433219（tab=2020_01, cat01=0=総数）、世帯数は 0003433220（tab=2020_13）
    stat_pop = _load_json(RAW_DIR / "census_2020_pop_0003433219.json")["GET_STATS_DATA"]["STATISTICAL_DATA"]
    leaf_pop = _leaf_area_codes(stat_pop["CLASS_INF"]["CLASS_OBJ"])
    pop = {v["@area"]: _to_num(v["$"]) for v in stat_pop["DATA_INF"]["VALUE"]
           if v["@tab"] == "2020_01" and v["@cat01"] == "0" and v["@area"] in leaf_pop}

    stat_hh = _load_json(RAW_DIR / "census_2020_0003433220.json")["GET_STATS_DATA"]["STATISTICAL_DATA"]
    leaf_hh = _leaf_area_codes(stat_hh["CLASS_INF"]["CLASS_OBJ"])
    hh = {v["@area"]: _to_num(v["$"]) for v in stat_hh["DATA_INF"]["VALUE"]
          if v["@tab"] == "2020_13" and v["@area"] in leaf_hh}
    area = {v["@area"]: _to_num(v["$"]) for v in stat_hh["DATA_INF"]["VALUE"]
            if v["@tab"] == "2020_47" and v["@area"] in leaf_hh}

    names_2020 = {**leaf_pop, **leaf_hh}
    for code in set(pop) | set(hh):
        rows.append({"year": 2020, "area_code": code, "area_name": names_2020[code],
                     "population": pop.get(code), "households": hh.get(code),
                     "area_km2": area.get(code)})

    return pd.DataFrame(rows)


# ---------- 2. 住宅着工件数 ----------

def load_housing_starts() -> pd.DataFrame:
    sources = [
        ("housing_starts_calendar_2011_2019_0003114492.json", "calendar"),
        ("housing_starts_fiscal_2020_2023_0004019381.json", "fiscal"),
    ]
    rows = []
    for fname, period_type in sources:
        stat = _load_json(RAW_DIR / fname)["GET_STATS_DATA"]["STATISTICAL_DATA"]
        leaf = _leaf_area_codes(stat["CLASS_INF"]["CLASS_OBJ"])
        agg: dict[tuple[str, int], dict[str, float]] = {}
        for v in stat["DATA_INF"]["VALUE"]:
            code = v["@area"]
            metric = HOUSING_TAB_METRICS.get(v["@tab"])
            if code not in leaf or v["@cat01"] not in RESIDENTIAL_CAT01 or metric is None:
                continue
            num = _to_num(v["$"])
            if num is None:
                continue
            year = int(v["@time"][:4])
            bucket = agg.setdefault((code, year), {})
            bucket[metric] = bucket.get(metric, 0.0) + num
        for (code, year), metrics in agg.items():
            rows.append({"year": year, "area_code": code, "area_name": leaf[code],
                         "period_type": period_type, **metrics})
    return pd.DataFrame(rows)


# ---------- 3. 公示地価（住宅地） ----------

def load_land_price() -> pd.DataFrame:
    frames = []
    for path in sorted(RAW_DIR.glob("land_price_*_div00.json")):
        year = int(path.name.split("_")[2])
        records = json.loads(path.read_text())
        df = pd.DataFrame(records)
        pref = df["標準地番号 市区町村コード 県コード"].astype(int).astype(str).str.zfill(2)
        muni = df["標準地番号 市区町村コード 市区町村コード"].astype(int).astype(str).str.zfill(3)
        df["area_code"] = pref + muni
        df["price_per_sqm"] = pd.to_numeric(df["1㎡当たりの価格"], errors="coerce")
        g = df.groupby("area_code")["price_per_sqm"].agg(
            land_price_mean_per_sqm="mean",
            land_price_median_per_sqm="median",
            land_price_n_points="count",
        ).reset_index()
        g["year"] = year
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


# ---------- 4. 持ち家/借家比率（2023年、単年横断データ） ----------

def load_housing_tenure() -> pd.DataFrame:
    """住宅の所有の関係（2023年住宅・土地統計調査、市区町村単位）を市区町村コード単位に整形する。

    公示地価と同様、この表も2023年単年の横断データしかなく、国勢調査の年次（2000〜2020）とは
    直接突合できない。直近の持ち家/借家構成として横断的に使う想定（DATA_PLANの地価と同じ扱い）。
    """
    stat = _load_json(RAW_DIR / "housing_tenure_detailed_0004021424.json")["GET_STATS_DATA"]["STATISTICAL_DATA"]
    leaf = _leaf_area_codes(stat["CLASS_INF"]["CLASS_OBJ"])

    agg: dict[str, dict[str, float]] = {}
    for v in stat["DATA_INF"]["VALUE"]:
        code = v["@area"]
        metric = TENURE_CAT02_METRICS.get(v["@cat02"])
        if code not in leaf or metric is None:
            continue
        num = _to_num(v["$"])
        if num is None:
            continue
        agg.setdefault(code, {})[metric] = num

    rows = []
    for code, metrics in agg.items():
        total = metrics.get("owned", 0.0) + metrics.get("rented_total", 0.0)
        row = {"area_code": code, "area_name": leaf[code], "housing_total": total, **metrics}
        if total:
            row["owned_ratio"] = metrics.get("owned", 0.0) / total
            row["rented_private_ratio"] = metrics.get("rented_private", 0.0) / total
        rows.append(row)
    return pd.DataFrame(rows)


# ---------- 5. 通勤時間中位数（都市圏へのアクセスの代理指標、2023年、単年横断データ） ----------

def load_commute() -> pd.DataFrame:
    """家計を主に支える者の通勤時間の中位数（分）を市区町村単位で整形する。

    持ち家/借家比率と同じ2023年住宅・土地統計調査由来で、単年の横断データ。値が小さいほど
    都市圏（雇用の中心）へのアクセスが良いと解釈する。cat01=0(男女総数), cat02=0(所有関係総数)
    のみ取得済み。
    """
    stat = _load_json(RAW_DIR / "commute_median_0004021694.json")["GET_STATS_DATA"]["STATISTICAL_DATA"]
    leaf = _leaf_area_codes(stat["CLASS_INF"]["CLASS_OBJ"])

    rows = []
    for v in stat["DATA_INF"]["VALUE"]:
        code = v["@area"]
        if code not in leaf:
            continue
        num = _to_num(v["$"])
        if num is None:
            continue
        rows.append({"area_code": code, "area_name": leaf[code], "commute_time_median_min": num})
    return pd.DataFrame(rows)


# ---------- 統合 ----------

def build_panel() -> pd.DataFrame:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    census = load_census()
    housing = load_housing_starts()
    land = load_land_price()
    tenure = load_housing_tenure()
    commute = load_commute()

    census.sort_values(["area_code", "year"]).to_csv(PROCESSED_DIR / "population_households.csv", index=False)
    housing.sort_values(["area_code", "year"]).to_csv(PROCESSED_DIR / "housing_starts.csv", index=False)
    land.sort_values(["area_code", "year"]).to_csv(PROCESSED_DIR / "land_price.csv", index=False)
    tenure.sort_values("area_code").to_csv(PROCESSED_DIR / "housing_tenure.csv", index=False)
    commute.sort_values("area_code").to_csv(PROCESSED_DIR / "commute.csv", index=False)

    panel = pd.merge(
        census[["year", "area_code", "area_name", "population", "households", "area_km2"]],
        housing.drop(columns=["area_name"]),
        on=["year", "area_code"], how="outer",
    )
    panel = pd.merge(panel, land, on=["year", "area_code"], how="outer")

    name_lookup = pd.concat([
        census[["area_code", "area_name"]],
        housing[["area_code", "area_name"]],
    ]).dropna().drop_duplicates("area_code").set_index("area_code")["area_name"]
    panel["area_name"] = panel["area_name"].fillna(panel["area_code"].map(name_lookup))

    panel = panel.sort_values(["area_code", "year"]).reset_index(drop=True)
    panel.to_csv(PROCESSED_DIR / "merged_panel.csv", index=False)
    return panel


if __name__ == "__main__":
    panel = build_panel()
    print(f"merged_panel: {panel.shape[0]} rows, {panel['area_code'].nunique()} municipalities, "
          f"years {sorted(panel['year'].dropna().unique())}")
    tenure = pd.read_csv(PROCESSED_DIR / "housing_tenure.csv")
    print(f"housing_tenure: {tenure.shape[0]} municipalities")
