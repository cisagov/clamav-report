#!/bin/bash
#
# Gather ClamAV scan log data from a list of AWS instances via SSM.
#
# Usage: ./clamav_log_report.sh <instance-id>...

set -o nounset
set -o errexit
set -o pipefail

if [ $# -eq 0 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  echo "Usage: $0 <instance-id>..."
  exit 1
fi

today=$(date +%Y%m%d)
logfile="./clamav-$today.log"
# tee -a: Append to existing logfile
# tee -i: Ignore SIGINT signals
exec > >(tee -ai "$logfile")
exec 2> >(tee -ai "$logfile" >&2)

clamav_scan_log="/var/log/clamav/lastscan.log"

instances=("$@")

for instance_id in "${instances[@]}"; do
  # tail --lines=12: Output last 12 lines of ClamAV scan log, which includes
  # the summary of the most-recent scan results.
  aws ssm start-session --target="$instance_id" \
    --document=AWS-StartInteractiveCommand \
    --parameters command="hostname; tail --lines=12 $clamav_scan_log"
done
