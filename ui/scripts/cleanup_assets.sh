#!/bin/bash

# Script to clean up attached_assets directory by parsing dates from filenames
# Usage: ./cleanup_assets.sh [days] [dry_run] [debug]
# Example: ./cleanup_assets.sh 30 true - Will show files older than 30 days but not delete them
# Example: ./cleanup_assets.sh 30 false - Will delete files older than 30 days
# Adding true as third parameter enables debug mode

# Default to 30 days if not specified
DAYS=${1:-30}
# Default to dry run if not specified
DRY_RUN=${2:-true}
# Debug mode
DEBUG_MODE=${3:-false}

ASSETS_DIR="./attached_assets"
CURRENT_DATE=$(date +%s)
CUTOFF_DATE=$((CURRENT_DATE - DAYS * 86400)) # Convert days to seconds

echo "Checking for files older than $DAYS days in $ASSETS_DIR"
echo "Current date: $(date -d @${CURRENT_DATE})"
echo "Cutoff date: $(date -d @${CUTOFF_DATE})"

if [ "$DRY_RUN" = "true" ]; then
  echo "DRY RUN MODE - No files will be deleted"
fi

if [ "$DEBUG_MODE" = "true" ]; then
  echo "DEBUG MODE - Showing detailed information"
fi

# Initialize counter
total_files=0
old_files=0

find "$ASSETS_DIR" -type f -not -name "README.md" -not -name ".gitkeep" | while read file; do
  filename=$(basename "$file")
  file_date=0
  date_source="unknown"
  
  # Parse date from screenshot filenames (format: Screenshot 2025-03-13 at 1.07.35 AM.png)
  if [[ $filename =~ Screenshot\ ([0-9]{4})-([0-9]{2})-([0-9]{2})\ at ]]; then
    year="${BASH_REMATCH[1]}"
    month="${BASH_REMATCH[2]}"
    day="${BASH_REMATCH[3]}"
    
    # Convert YY-MM-DD to timestamp for comparison
    file_date=$(date -d "$year-$month-$day" +%s 2>/dev/null)
    date_source="filename-screenshot"
    
    # Fallback to file modification time if date parsing fails
    if [ $? -ne 0 ]; then
      file_date=$(stat -c %Y "$file")
      date_source="fallback-mtime"
    fi
  # Parse date from Pasted filenames (format: Pasted--npx-jest-coverage-...-1741838964774.txt)
  elif [[ $filename =~ Pasted.*-([0-9]{13})\.txt$ ]]; then
    timestamp="${BASH_REMATCH[1]}"
    # Convert milliseconds to seconds (Unix timestamp)
    file_date=$((timestamp / 1000))
    date_source="filename-timestamp"
  # For other files, use file modification time
  else
    file_date=$(stat -c %Y "$file")
    date_source="file-mtime"
  fi
  
  # Calculate age in days
  age_days=$(( (CURRENT_DATE - file_date) / 86400 ))
  
  # Increment counter
  total_files=$((total_files + 1))
  
  if [ "$DEBUG_MODE" = "true" ]; then
    echo "File: $filename"
    echo "  Date source: $date_source"
    echo "  File date: $(date -d @${file_date})"
    echo "  Age: $age_days days"
    echo "  Cutoff: $DAYS days"
    echo "  Result: $([ $file_date -lt $CUTOFF_DATE ] && echo "OLD" || echo "KEEP")"
    echo ""
  fi
  
  # Check if file is older than the cutoff date
  if [ $file_date -lt $CUTOFF_DATE ]; then
    # Increment old files counter
    old_files=$((old_files + 1))
    
    if [ "$DRY_RUN" = "true" ]; then
      echo "Would delete: $file (approx. $age_days days old)"
    else
      echo "Deleting: $file (approx. $age_days days old)"
      rm "$file"
    fi
  fi
done

echo "Total files checked: $total_files"
echo "Files older than $DAYS days: $old_files"
echo "Operation complete."