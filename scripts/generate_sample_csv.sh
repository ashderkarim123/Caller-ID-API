#!/bin/bash
# Generate sample CSV files with caller-IDs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/../data"

# Create data directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

echo "Generating sample CSV files..."

# Generate small sample (100 records)
python3 "$SCRIPT_DIR/bulk_import.py" \
    --generate-sample "$OUTPUT_DIR/sample_caller_ids_100.csv" \
    --sample-count 100

echo "✓ Generated: $OUTPUT_DIR/sample_caller_ids_100.csv (100 records)"

# Generate medium sample (1,000 records)
python3 "$SCRIPT_DIR/bulk_import.py" \
    --generate-sample "$OUTPUT_DIR/sample_caller_ids_1000.csv" \
    --sample-count 1000

echo "✓ Generated: $OUTPUT_DIR/sample_caller_ids_1000.csv (1,000 records)"

# Generate large sample (10,000 records)
python3 "$SCRIPT_DIR/bulk_import.py" \
    --generate-sample "$OUTPUT_DIR/sample_caller_ids_10000.csv" \
    --sample-count 10000

echo "✓ Generated: $OUTPUT_DIR/sample_caller_ids_10000.csv (10,000 records)"

echo ""
echo "Sample CSV files generated successfully!"
echo "Location: $OUTPUT_DIR/"
echo ""
echo "To import, run:"
echo "  python3 $SCRIPT_DIR/bulk_import.py --csv $OUTPUT_DIR/sample_caller_ids_100.csv --method db"
