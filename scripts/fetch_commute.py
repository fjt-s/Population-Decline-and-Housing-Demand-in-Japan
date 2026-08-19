"""通勤時間中位数（都市圏へのアクセスの代理指標、市区町村別）を e-Stat API から取得する。

README記載の3つの仮説（世帯数増加／地価／都市圏へのアクセス）のうち、まだ検証していなかった
「都市圏へのアクセス」用のデータ。2023年住宅・土地統計調査（00200522）に、家計を主に支える者の
通勤時間の中位数を市区町村単位で持つ表がある（searchWord="所有の関係 市区町村" surveyYears=202310
で見つけた 0004021694）。

cat01（性別）=0（総数）、cat02（住宅の所有の関係）=0（総数）に絞って取得する
（絞らないと area(1283)×cat01(3)×cat02(7) の全組み合わせになるため）。

使い方（.env に ESTAT_APP_ID を設定した状態で）:
    python scripts/fetch_commute.py
"""
import json
from pathlib import Path

from estat_client import get_stats_data

COMMUTE_TABLE = "0004021694"

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch():
    data = get_stats_data(COMMUTE_TABLE, cdCat01="0", cdCat02="0")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"commute_median_{COMMUTE_TABLE}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    fetch()
