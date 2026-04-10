#!/bin/bash

check_host() {
  local i=$1
  local host="research-common-${i}"
  output=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes "$host" \
    'nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits' 2>/dev/null)
  if [ $? -ne 0 ]; then
    printf "%-25s UNREACHABLE\n" "$host"
    return
  fi
  busy=0; total=0
  while IFS=', ' read -r idx mem_used mem_total gpu_util; do
    total=$((total + 1))
    if [ "$mem_used" -gt 100 ] 2>/dev/null; then
      busy=$((busy + 1))
    fi
  done <<< "$output"
  free=$((total - busy))
  if [ "$busy" -eq 0 ]; then
    printf "%-25s EMPTY (%d GPUs free)\n" "$host" "$total"
  elif [ "$free" -gt 0 ]; then
    printf "%-25s PARTIAL (%d/%d GPUs free)\n" "$host" "$free" "$total"
  else
    printf "%-25s FULL (%d GPUs busy)\n" "$host" "$total"
  fi
}

for i in $(seq -w 1 33); do
  check_host "$i" &
done
wait
