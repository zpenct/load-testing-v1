#!/bin/bash
# Usage:
#   ./run_all.sh --env .env.test
#   ./run_all.sh --env .env.poc
#   ./run_all.sh http://localhost:8000

RAG_URL="http://localhost:8000"
INFLUX_URL="http://localhost:8086/k6"

if [[ "$1" == "--env" && -f "$2" ]]; then
  echo "📦 Loading env from: $2"
  export $(grep -v '^#' "$2" | xargs)
  RAG_URL=${RAG_URL:-"http://localhost:8000"}
  INFLUX_URL=${INFLUX_URL:-"http://localhost:8086/k6"}
elif [[ -n "$1" ]]; then
  RAG_URL=$1
fi

# Buat folder output
mkdir -p reports summarizer tmp

# Nama file report gabungan (satu per run)
REPORT_FILE="reports/load_test_report_$(date +%Y%m%d_%H%M%S).md"
export REPORT_FILE

echo "========================================"
echo "🚀 RAG Load Testing Suite"
echo "   Target  : $RAG_URL"
echo "   InfluxDB: $INFLUX_URL"
echo "   Report  : $REPORT_FILE"
echo "========================================"

run_test() {
  local scenario=$1   # "01"
  local name=$2       # "01_smoke"
  local script=$3     # "01_smoke.js"
  local summary_json="tmp/summary_${name}.json"

  echo ""
  echo "▶ Running: $name"
  echo "----------------------------------------"

  k6 run \
    --out influxdb=$INFLUX_URL \
    --summary-export "$summary_json" \
    --env RAG_URL=$RAG_URL \
    --tag testid="${name}_$(date +%Y%m%d_%H%M%S)" \
    "scripts/$script"

  # Generate summary section
  if [[ -f "$summary_json" ]]; then
    python3 summarizer/summarize.py \
      --scenario "$scenario" \
      --input "$summary_json" \
      --report "$REPORT_FILE"
  else
    echo "⚠️  Summary JSON tidak ditemukan untuk $name"
  fi

  echo "✓ Done: $name — cooldown 30s..."
  sleep 30
}

run_test "01" "01_smoke"             "01_smoke.js"
run_test "02" "02_baseline_intent"   "02_baseline_intent.js"
run_test "03" "03_concurrency_sweep" "03_concurrency_sweep.js"
run_test "04" "04_stream_ttft"       "04_stream_ttft.js"
run_test "05" "05_spike"             "05_spike.js"
run_test "06" "06_soak"              "06_soak.js"

echo ""
echo "========================================"
echo "✅ All tests complete!"
echo "📄 Report: $REPORT_FILE"
echo "📊 Dashboard: http://localhost:3001"
echo "========================================"