# Population Decline and Housing Demand in Japan

## Motivation

石川への帰省時に、人口減少地域であっても新築戸建て住宅が数多く建設されていることに疑問を持った。

本分析では、人口減少下でも住宅着工が維持される地域の特徴を明らかにすることを目的とする。

## Research Question

人口減少率だけで住宅着工件数を説明できるのか？

## Hypotheses

- 核家族化の進展に伴う世帯数増加が関係している
- 地価が関係している
- 都市圏へのアクセスが関係している

## Data Sources

- e-Stat
- 国勢調査
- 住宅着工統計
- 公示地価
- 住宅・土地統計調査（持ち家/借家比率、通勤時間中位数）

## Findings（要約）

人口減少率だけでは住宅着工を十分に説明できない。人口密度で自治体を区分すると、都市部では
人口動態と着工が強く連動する一方、農山村・過疎的な地域ではその連動が弱い。地価・都市圏アクセス
（通勤時間）・持ち家率という3つの候補のうち、頑健性確認（対数変換DVでの再推定）まで通ったのは
**持ち家率（戸建て信仰）のみ**。地方における住宅着工は、人口動態に応じた市場的な需給調整という
より、持ち家取得というライフイベントに駆動されている可能性が高い。

詳細な分析結果・図表・限界は **[docs/REPORT.md](docs/REPORT.md)** を参照。

## Status

- [x] Data collection
- [x] Data cleaning
- [x] Exploratory analysis
- [x] Statistical modeling
- [x] Final report
