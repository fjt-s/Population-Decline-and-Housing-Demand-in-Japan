"""持ち家/借家比率（住宅の所有の関係、市区町村別）を e-Stat API から取得する。

2023年住宅・土地統計調査（00200522）の中から、市区町村単位で「住宅の所有の関係」別の
住宅数が取れる表を searchWord="所有の関係 市区町村" surveyYears=202310 で検索して特定した。

- SIMPLE_TABLE (0004021628): 所有の関係 2区分（持ち家／借家）。まずはこちらで軽く検証する。
- DETAILED_TABLE (0004021424): 所有の関係 5区分（持ち家／公営借家／UR・公社借家／民営借家／給与住宅）。
  簡易版で見込みがあれば、内訳を見るためにこちらも取得する。

使い方（.env に ESTAT_APP_ID を設定した状態で）:
    python scripts/fetch_housing_tenure.py fetch-simple
    python scripts/fetch_housing_tenure.py fetch-detailed
"""
import json
import sys
from pathlib import Path

from estat_client import get_stats_data

SIMPLE_TABLE = "0004021628"
DETAILED_TABLE = "0004021424"

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch(stats_data_id: str, name: str, **params):
    data = get_stats_data(stats_data_id, **params)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"housing_tenure_{name}_{stats_data_id}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch-simple"
    if cmd == "fetch-simple":
        fetch(SIMPLE_TABLE, "simple")
    elif cmd == "fetch-detailed":
        # 無条件だと tab(8)×cat01(3)×cat02(7)×cat03(5)×area(1283) の全組み合わせが
        # 100万件超になり1リクエスト上限(10万件)を超えるため、必要な断面だけAPI側で絞り込む。
        # tab=01-2023(住宅数), cat01=0(総数=専用+店舗併用), cat03=0(総数=建て方問わず),
        # cat02=1,2,21,22,23,24(所有の関係の実区分。0=総数は持ち家+借家から算出できるので除く)
        fetch(DETAILED_TABLE, "detailed", cdTab="01-2023", cdCat01="0", cdCat03="0",
              cdCat02="1,2,21,22,23,24")
    else:
        print("usage: fetch_housing_tenure.py [fetch-simple|fetch-detailed]")
