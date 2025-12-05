#!/bin/bash
# Helper script to import CSV file into the API container

if [ $# -lt 1 ]; then
    echo "Usage: $0 <csv_file>"
    echo "Example: $0 /path/to/caller_ids.csv"
    exit 1
fi

CSV_FILE="$1"

if [ ! -f "$CSV_FILE" ]; then
    echo "Error: CSV file not found: $CSV_FILE"
    exit 1
fi

echo "Copying CSV file to container..."
docker compose cp "$CSV_FILE" api:/tmp/caller_ids.csv

echo "Running import..."
docker compose exec api python bulk_import.py /tmp/caller_ids.csv

echo "Cleaning up..."
docker compose exec api rm /tmp/caller_ids.csv

echo "Done!"
