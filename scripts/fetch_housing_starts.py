"""住宅着工件数（市区町村別）を e-Stat API から取得する。

政府統計コード 00600120 = 建築着工統計調査。

「住宅着工統計」本体の確報（新設住宅着工戸数）は都道府県別までしか出ないため、
市区町村単位では「建築物着工統計 表7-2」（市区町村別、用途別（大分類）／建築物の数・
床面積・工事費予定額）を使う。cat01（用途）のうち下記3コードが住宅系:
    12: 居住専用住宅, 13: 居住専用準住宅, 14: 居住産業併用建築物
→ 「新設住宅着工戸数」とは集計定義が異なる近似値である点に注意（厳密な住宅着工件数ではない）。

【データの空白と接続の注意】
- 市区町村別のこの粒度は 2011年分以降のみ e-Stat 上で提供されている（2000〜2010年は無い）。
  国勢調査は2000年から取れるが、住宅着工の市区町村別データは2011年からしか揃わない。
- 統計表が「暦年」基準（〜2019年）と「年度」基準（2020年度〜）で分かれている
  （2020年の建築基準法別表改正に伴う区分変更）。年next基準が変わる点に注意して結合すること。

使い方（.env に ESTAT_APP_ID を設定した状態で）:
    python scripts/fetch_housing_starts.py fetch-all
    python scripts/fetch_housing_starts.py list [year]
"""
import json
import sys
from pathlib import Path

from estat_client import get_stats_data_all, get_stats_list

STATS_CODE = "00600120"  # 建築着工統計調査

# 建築物着工統計 表7-2（市区町村別、用途別（大分類）／建築物の数、床面積、工事費予定額）
HOUSING_STARTS_TABLES = {
    "calendar_2011_2019": "0003114492",  # 暦年基準、2011〜2019年
    "fiscal_2011_2019": "0003117502",  # 年度基準、2011〜2019年度（参考。基本は calendar 版を使う）
    "fiscal_2020_2023": "0004019381",  # 年度基準、2020〜2023年度（区分改定後）
}

RESIDENTIAL_CAT01_CODES = ["12", "13", "14"]

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def list_tables(year: int | None = None):
    params = {"searchWord": "市区町村別 用途別 建築物"}
    if year:
        params["surveyYears"] = year
    res = get_stats_list(STATS_CODE, **params)
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


def fetch(key: str):
    stats_data_id = HOUSING_STARTS_TABLES[key]
    data = get_stats_data_all(stats_data_id)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"housing_starts_{key}_{stats_data_id}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


def fetch_all():
    for key in HOUSING_STARTS_TABLES:
        fetch(key)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch-all"
    if cmd == "fetch-all":
        fetch_all()
    elif cmd == "fetch":
        fetch(sys.argv[2])
    elif cmd == "list":
        list_tables(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        print("usage: fetch_housing_starts.py [fetch-all|fetch <key>|list [year]]")
