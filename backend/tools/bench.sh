#!/usr/bin/env bash
# Benchmark under the evaluation budget: 2 pinned CPUs, 4 GB address space, wall clock and
# peak RSS of the whole run. Optionally a scaled dataset to estimate the growth exponent.
#
#   bash tools/bench.sh <input_dir> [<large_input_dir>]
#
# Prints only timings and memory. Development tool, not part of the pipeline.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$HERE/.venv/bin/python}"
CPUS="${BENCH_CPUS:-0,1}"
MEM_KB="${BENCH_MEM_KB:-4194304}"

run() {
  local inp="$1" out
  out="$(mktemp -d)"
  rm -rf "$out"
  local log
  log="$(mktemp)"
  ( ulimit -v "$MEM_KB"; RAKSHA_SECRET=bench taskset -c "$CPUS" /usr/bin/time -v \
      "$PY" "$HERE/main.py" --input "$inp" --output "$out" ) >/dev/null 2>"$log" || true
  local wall rss code files
  wall=$(grep "Elapsed (wall clock)" "$log" | awk '{print $NF}')
  rss=$(grep "Maximum resident set size" "$log" | awk '{print $NF}')
  code=$(grep "Exit status" "$log" | awk '{print $NF}')
  files=$(find "$inp" -type f | wc -l)
  echo "files=$files exit=$code wall=$wall peak_rss_mb=$((rss / 1024)) cpus=$CPUS mem_cap_mb=$((MEM_KB / 1024))"
  rm -rf "$out" "$log"
}

echo "BENCH (2 CPUs pinned, 4 GB cap)"
run "$1"
if [[ $# -ge 2 ]]; then
  run "$2"
fi
