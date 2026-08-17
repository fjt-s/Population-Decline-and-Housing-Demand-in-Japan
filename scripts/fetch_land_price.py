"""公示地価・地価調査（全国、市区町村コード付き）を不動産情報ライブラリ API から取得する。

XCT001（鑑定評価書情報API）を都道府県コード（01〜47）でループして全国を取得する。
レスポンスに市区町村コードが含まれるため、市区町村単位への集計はこの後の前処理で行う。

【制約】year は 2022〜2026 のみ指定可能（2026年8月時点のAPI仕様）。国勢調査（2000-2020）
と直接時系列を揃えられないため、分析では「直近の地価水準」として横断的に使うか、
より古い年が必要なら XPT002（タイル方式、1995〜2024年）での補完取得を検討する
（reinfolib_client.get_land_price_tile を参照）。

使い方（APIキー発行後）:
    python scripts/fetch_land_price.py 2024
    python scripts/fetch_land_price.py 2024 --division 00   # 00=住宅地(デフォルト), 05=商業地, 09=工業地
"""
import json
import sys
import time
from pathlib import Path

from reinfolib_client import PREFECTURE_CODES, get_appraisal_reports

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch_year(year: int, division: str = "00") -> list:
    records = []
    for pref_code in PREFECTURE_CODES:
        try:
            res = get_appraisal_reports(year=year, area=pref_code, division=division)
        except Exception as e:
            print(f"  pref {pref_code} skipped: {e}")
            continue
        items = res if isinstance(res, list) else res.get("data", res)
        n = len(items) if hasattr(items, "__len__") else 0
        print(f"  pref {pref_code}: {n} records")
        if isinstance(items, list):
            records.extend(items)
        time.sleep(0.2)  # 連続リクエストを避ける
    return records


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: fetch_land_price.py <year> [--division CODE]")
        sys.exit(1)
    year = int(sys.argv[1])
    division = "00"
    if "--division" in sys.argv:
        division = sys.argv[sys.argv.index("--division") + 1]

    result = fetch_year(year, division)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"land_price_{year}_div{division}.json"
    out.write_text(json.dumps(result, ensure_ascii=False))
    print(f"saved: {out} ({len(result)} records)")
