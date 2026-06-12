#!/bin/sh
# smoke 캡처: 주요 엔드포인트 응답을 지정 디렉토리에 저장
# 사용: sh scripts/smoke_capture.sh <outdir>
set -u
OUT="$1"
mkdir -p "$OUT"
BASE="http://localhost:39745/api/v1"

# 서버 준비 대기 (최대 120초)
i=0
until curl -sf "$BASE/commodities" > /dev/null 2>&1; do
  i=$((i+5))
  if [ "$i" -gt 120 ]; then echo "SERVER NOT READY"; exit 1; fi
  sleep 5
done

ep() {
  name="$1"; path="$2"
  curl -s "$BASE$path" | python -c "import json,sys; print(json.dumps(json.load(sys.stdin), ensure_ascii=False, sort_keys=True, indent=1))" > "$OUT/$name.json" 2>"$OUT/$name.err" || echo "FAIL $name"
}

ep commodities "/commodities"
ep commodity_wheat "/commodities/wheat"
ep stream_wheat "/commodities/wheat/stream"
ep stream_minimap "/commodities/wheat/stream/minimap"
ep scatter_wheat "/commodities/wheat/scatter"
ep raw_prices "/commodities/wheat/raw-prices"
ep raw_minimap "/commodities/wheat/raw-prices/minimap"
ep anomaly_summary "/anomalies/summary"
ep meta_config "/meta/config"
ep meta_pipeline "/meta/pipeline"
ep meta_params "/meta/analysis-params"
ep freshness "/freshness"
ep events "/events"
ep segments "/segments"
echo "captured -> $OUT"
ls "$OUT" | wc -l
