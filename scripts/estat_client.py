"""e-Stat API (3.0) の薄いラッパー。

appId は環境変数 ESTAT_APP_ID から読む（.env 対応）。
https://www.e-stat.go.jp/api/api-info/e-stat-manual3-0
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json"


def _app_id() -> str:
    app_id = os.environ.get("ESTAT_APP_ID")
    if not app_id:
        raise RuntimeError("ESTAT_APP_ID が未設定です。.env を確認してください。")
    return app_id


def get_stats_list(stats_code: str, **params) -> dict:
    """statsCode（政府統計コード）に紐づく統計表の一覧を取得する。

    例: statsCode="00200521" -> 国勢調査関連の統計表一覧
    """
    r = requests.get(
        f"{BASE_URL}/getStatsList",
        params={"appId": _app_id(), "statsCode": stats_code, **params},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_stats_data(stats_data_id: str, **params) -> dict:
    """statsDataId で指定した統計表の実データを取得する（1リクエスト分、最大10万件）。"""
    r = requests.get(
        f"{BASE_URL}/getStatsData",
        params={"appId": _app_id(), "statsDataId": stats_data_id, **params},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def get_stats_data_all(stats_data_id: str, **params) -> dict:
    """statsDataId の実データを、1リクエストの上限（10万件）を超える分も含めて全件取得する。

    RESULT_INF.NEXT_KEY がある限り startPosition を進めながらページングし、
    VALUE 配列を結合した1つのレスポンスとして返す（RESULT_INF は最後のページのものになる）。
    """
    data = get_stats_data(stats_data_id, **params)
    stat_data = data["GET_STATS_DATA"]["STATISTICAL_DATA"]
    values = stat_data["DATA_INF"]["VALUE"]
    next_key = stat_data.get("RESULT_INF", {}).get("NEXT_KEY")
    while next_key:
        page = get_stats_data(stats_data_id, startPosition=next_key, **params)
        page_stat_data = page["GET_STATS_DATA"]["STATISTICAL_DATA"]
        values.extend(page_stat_data["DATA_INF"]["VALUE"])
        next_key = page_stat_data.get("RESULT_INF", {}).get("NEXT_KEY")
        stat_data["RESULT_INF"] = page_stat_data.get("RESULT_INF", {})
    stat_data["DATA_INF"]["VALUE"] = values
    return data


if __name__ == "__main__":
    import json
    import sys

    # 動作確認用: 政府統計コードを引数で渡すと、紐づく統計表一覧を表示する。
    # 使い方: python scripts/estat_client.py 00200521
    code = sys.argv[1] if len(sys.argv) > 1 else "00200521"
    data = get_stats_list(code)
    print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
