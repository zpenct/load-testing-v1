#!/bin/bash
# Usage:
#   ./run_all.sh --env .env.test
#   ./run_all.sh --env .env.poc
#   ./run_all.sh http://localhost:8000

#!/bin/bash
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

mkdir -p reports summarizer tmp

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="reports/load_test_report_${TIMESTAMP}.md"
SESSION_DIR="reports/raw/${TIMESTAMP}" 
export REPORT_FILE SESSION_DIR TIMESTAMP

echo "========================================"
echo "🚀 RAG Load Testing Suite"
echo "   Target    : $RAG_URL"
echo "   Report     : $REPORT_FILE"
echo "   Raw output : $SESSION_DIR"
echo "========================================"

# Simpan session metadata
mkdir -p "$SESSION_DIR"
python3 -c "
import json, os
from datetime import datetime
meta = {
    'session_id':   os.environ.get('TIMESTAMP'),
    'rag_url':      os.environ.get('RAG_URL'),
    'influx_url':   os.environ.get('INFLUX_URL'),
    'started_at':   datetime.now().isoformat(),
    'skenario_run': ['01','02','03','04','05','06'],
}
with open(f\"{os.environ.get('SESSION_DIR')}/session_meta.json\", 'w') as f:
    json.dump(meta, f, indent=2)
print('[session] ✅ session_meta.json created')
"

run_test() {
  local scenario=$1
  local name=$2
  local script=$3
  local summary_json="tmp/summary_${name}.json"

  echo ""
  echo "▶ Running: $name"
  echo "----------------------------------------"

  k6 run \
    --out influxdb=$INFLUX_URL \
    --summary-export "$summary_json" \
    --env RAG_URL=$RAG_URL \
    --tag testid="${name}_${TIMESTAMP}" \
    "scripts/$script"

  # Generate summary section (human-readable .md)
  if [[ -f "$summary_json" ]]; then
    python3 summarizer/summarize.py \
      --scenario "$scenario" \
      --input "$summary_json" \
      --report "$REPORT_FILE"

    # Simpan raw JSON lengkap
    python3 summarizer/store_raw.py \
      --scenario "$scenario" \
      --input "$summary_json" \
      --session-dir "$SESSION_DIR" \
      --rag-url "$RAG_URL" \
      --influx-url "$INFLUX_URL"
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
echo ""
echo "📄 Summary Report : $REPORT_FILE"
echo "📦 Raw Files      : $SESSION_DIR/"
echo "📊 Dashboard      : http://localhost:3001"
echo "========================================"