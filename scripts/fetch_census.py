"""国勢調査（人口・世帯数、市区町村別）を e-Stat API から取得する。

CENSUS_TABLES は、各国勢調査年について
「人口・世帯数・5年間の増減率・面積・人口密度－全国，都道府県，市区町村」に相当する
統計表を searchWord="人口 世帯数 増減率 市区町村" で検索して特定した statsDataId。
市区町村コード（@area, 5桁）単位でレコードが返ることを 2020年分で確認済み。

使い方（.env に ESTAT_APP_ID を設定した状態で）:
    python scripts/fetch_census.py fetch-all      # 5年分まとめて取得して data/raw に保存
    python scripts/fetch_census.py fetch 2020     # 1年分だけ
    python scripts/fetch_census.py list [year]    # 統計表を再探索したいとき
"""
import json
import sys
from pathlib import Path

from estat_client import get_stats_data, get_stats_list

STATS_CODE = "00200521"  # 国勢調査

# 年 -> 統計表ID（人口・世帯数・増減率・面積・人口密度、市区町村単位）
CENSUS_TABLES = {
    2000: "0003391075",
    2005: "0003408216",
    2010: "0003411171",
    2015: "0003148500",
    2020: "0003433220",
}

# 2020年は 0003433220 に現数値の総人口（tab）が含まれていない（2015年組替人口のみ）ため、
# 男女別人口表 0003433219（tab=2020_01, cat01=0 が総数）から現数値人口を補う。
CENSUS_2020_POPULATION_TABLE = "0003433219"

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def list_tables(year: int | None = None):
    years = [year] if year else list(CENSUS_TABLES)
    for y in years:
        print(f"\n=== {y}年 ===")
        res = get_stats_list(STATS_CODE, searchWord="人口 世帯数 増減率 市区町村", surveyYears=y)
        tables = res.get("GET_STATS_LIST", {}).get("DATALIST_INF", {}).get("TABLE_INF", [])
        if isinstance(tables, dict):
            tables = [tables]
        seen = {}
        for t in tables:
            seen[t.get("@id")] = t
        for tid, t in seen.items():
            title = t.get("TITLE")
            title = title if isinstance(title, str) else title.get("$")
            print(tid, "-", title)


def fetch(year: int):
    stats_data_id = CENSUS_TABLES[year]
    data = get_stats_data(stats_data_id)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"census_{year}_{stats_data_id}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


def fetch_2020_population():
    stats_data_id = CENSUS_2020_POPULATION_TABLE
    data = get_stats_data(stats_data_id)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"census_2020_pop_{stats_data_id}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


def fetch_all():
    for year in CENSUS_TABLES:
        fetch(year)
    fetch_2020_population()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch-all"
    if cmd == "fetch-all":
        fetch_all()
    elif cmd == "fetch":
        fetch(int(sys.argv[2]))
    elif cmd == "list":
        list_tables(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        print("usage: fetch_census.py [fetch-all|fetch <year>|list [year]]")
