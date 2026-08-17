"""国勢調査（人口・世帯数、市区町村別）の統計表を e-Stat API から探索・取得する。

まだ appId が無い段階でも構造は組んである。appId 発行後は:
    python scripts/fetch_census.py list            # 対象年ごとの統計表一覧（statsDataId）を確認
    python scripts/fetch_census.py fetch <statsDataId>  # 実データを取得して data/raw に保存

政府統計コード 00200521 = 国勢調査。年ごとの統計表は getStatsList の surveyYears で絞り込み、
出てきた statsDataId を確認したうえで fetch する（表構成が年によって変わるため自動一本化はしない）。
"""
import json
import sys
from pathlib import Path

from estat_client import get_stats_data, get_stats_list

STATS_CODE = "00200521"  # 国勢調査
TARGET_YEARS = [2000, 2005, 2010, 2015, 2020]  # 2025年国勢調査は結果公表後に追加

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def list_tables():
    for year in TARGET_YEARS:
        print(f"\n=== {year}年 ===")
        res = get_stats_list(STATS_CODE, surveyYears=year)
        tables = (
            res.get("GET_STATS_LIST", {})
            .get("DATALIST_INF", {})
            .get("TABLE_INF", [])
        )
        if isinstance(tables, dict):
            tables = [tables]
        for t in tables[:20]:
            print(t.get("@id"), "-", t.get("STATISTICS_NAME"), "/", t.get("TITLE"))


def fetch(stats_data_id: str):
    data = get_stats_data(stats_data_id)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"census_{stats_data_id}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        list_tables()
    elif cmd == "fetch":
        fetch(sys.argv[2])
    else:
        print("usage: fetch_census.py [list|fetch <statsDataId>]")
