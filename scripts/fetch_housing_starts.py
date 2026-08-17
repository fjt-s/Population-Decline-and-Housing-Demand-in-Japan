"""住宅着工件数の統計表を e-Stat API から探索・取得する。

政府統計コード 00600120 = 建築着工統計調査。

【要確認・粒度の注意】
- 「住宅着工統計」自体の確報表（新設住宅着工戸数など）は都道府県別までしか出ない。
- 市区町村別の内訳が欲しい場合は「建築物着工統計」表7-2
  （市区町村別、用途別（大分類）／建築物の数、床面積、工事費予定額）を使う必要がある。
  ここでの「用途」区分に居住専用等が含まれるが、住宅着工統計の「新設住宅着工戸数」とは
  集計定義が異なる点に注意（＝厳密な住宅着工戸数ではなく建築物ベースの近似になる）。
- 都道府県単位の分析で足りるなら住宅着工統計を、市区町村単位が必要なら建築物着工統計を使う。
  → 分析の地域粒度が決まり次第、どちらを使うか確定させる。

使い方（appId 発行後）:
    python scripts/fetch_housing_starts.py list
    python scripts/fetch_housing_starts.py fetch <statsDataId>
"""
import json
import sys
from pathlib import Path

from estat_client import get_stats_data, get_stats_list

STATS_CODE = "00600120"  # 建築着工統計調査

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def list_tables(**params):
    res = get_stats_list(STATS_CODE, **params)
    tables = (
        res.get("GET_STATS_LIST", {})
        .get("DATALIST_INF", {})
        .get("TABLE_INF", [])
    )
    if isinstance(tables, dict):
        tables = [tables]
    for t in tables[:50]:
        print(t.get("@id"), "-", t.get("STATISTICS_NAME"), "/", t.get("TITLE"))


def fetch(stats_data_id: str):
    data = get_stats_data(stats_data_id)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"housing_starts_{stats_data_id}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        list_tables()
    elif cmd == "fetch":
        fetch(sys.argv[2])
    else:
        print("usage: fetch_housing_starts.py [list|fetch <statsDataId>]")
