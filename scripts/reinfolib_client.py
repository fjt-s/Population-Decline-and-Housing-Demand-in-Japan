"""国土交通省「不動産情報ライブラリ」API の薄いラッパー。

地価公示・地価調査データを取得する方法は2種類ある:

- XCT001（鑑定評価書情報API）: 都道府県コード指定で取得できる非タイル方式。全国を47都道府県
  ループで取得できるため基本はこちらを使う。ただし year は 2022〜2026 のみ指定可能（要注意）。
- XPT002（地価公示・地価調査のポイントAPI）: XYZタイル方式。1995〜2024年の長期データが
  取れる一方、全国をカバーするには膨大な数のタイルを走査する必要があるため、長期の時系列が
  必要になった場合の補完手段として残す。

API key は環境変数 REINFOLIB_API_KEY から読む（.env 対応）。
https://www.reinfolib.mlit.go.jp/help/apiManual/
"""
import math
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"


def _headers() -> dict:
    api_key = os.environ.get("REINFOLIB_API_KEY")
    if not api_key:
        raise RuntimeError("REINFOLIB_API_KEY が未設定です。.env を確認してください。")
    return {"Ocp-Apim-Subscription-Key": api_key}


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    """緯度経度をズームレベル z のタイル座標 (x, y) に変換する（Web メルカトル）。"""
    lat_rad = math.radians(lat)
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tiles_for_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float, z: int):
    """bbox（南西・北東の緯度経度）を覆うタイル座標 (x, y) を列挙する。"""
    x0, y1 = lonlat_to_tile(min_lon, min_lat, z)  # 南西
    x1, y0 = lonlat_to_tile(max_lon, max_lat, z)  # 北東
    for x in range(min(x0, x1), max(x0, x1) + 1):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            yield x, y


def get_land_price_tile(z: int, x: int, y: int, year: int, response_format: str = "geojson", **params) -> dict:
    """地価公示・地価調査のポイントデータ（1タイル分、XPT002）。長期時系列が必要な場合の補完用。"""
    r = requests.get(
        f"{BASE_URL}/XPT002",
        headers=_headers(),
        params={"response_format": response_format, "z": z, "x": x, "y": y, "year": year, **params},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


PREFECTURE_CODES = [f"{i:02d}" for i in range(1, 48)]  # 01(北海道)〜47(沖縄県)


def get_appraisal_reports(year: int, area: str, division: str = "00", **params) -> dict:
    """鑑定評価書情報（地価公示・地価調査、XCT001）を都道府県コード指定で取得する。

    area: 都道府県コード（2桁）。複数はカンマ区切り（例: "01,02,03"）。
    division: 用途区分（00=住宅地, 05=商業地, 09=工業地 など）。
    year: 2022〜2026 のみ指定可能（API仕様上の制約、2026年8月時点）。
    """
    r = requests.get(
        f"{BASE_URL}/XCT001",
        headers=_headers(),
        params={"year": year, "area": area, "division": division, **params},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    import json

    # 動作確認用: 石川県（コード17）の住宅地、2024年分を1都道府県だけ取得する。
    data = get_appraisal_reports(year=2024, area="17", division="00")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
