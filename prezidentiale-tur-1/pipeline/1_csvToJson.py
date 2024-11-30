# Full script as requested

import os
import pandas as pd
import json
from datetime import datetime

# Define the directory containing the CSV files
directory_path = "extrase-meta"

# Load and merge all CSV files from the specified directory
all_dataframes = []
for file in os.listdir(directory_path):
    if file.endswith('.csv'):
        file_path = os.path.join(directory_path, file)
        try:
            df = pd.read_csv(file_path)
            all_dataframes.append(df)
        except Exception as e:
            print(f"Error processing {file}: {e}")

# Concatenate all dataframes
merged_df = pd.concat(all_dataframes, ignore_index=True)

# Filter out rows where 'ad_delivery_stop_time' is before '2024-11-22'
if 'ad_delivery_stop_time' in merged_df.columns:
    merged_df['ad_delivery_stop_time'] = pd.to_datetime(
        merged_df['ad_delivery_stop_time'], errors='coerce'
    )
    merged_df = merged_df[
        (merged_df['ad_delivery_stop_time'].isna()) |
        (merged_df['ad_delivery_stop_time'] >= datetime(2024, 11, 22))
    ]

# Remove duplicates based on 'ad_archive_id'
merged_df = merged_df.drop_duplicates(subset=['ad_archive_id'])

# Process nested JSON fields: 'demographic_distribution' and 'delivery_by_region'
def process_nested_json(column):
    if column in merged_df.columns:
        merged_df[column] = merged_df[column].apply(
            lambda x: json.loads(f"[{x}]") if isinstance(x, str) else None
        )

process_nested_json('demographic_distribution')
process_nested_json('delivery_by_region')


# Enrich 'impressions' and 'spend' by converting to objects and calculating averages
def process_bounds_column(column):
    if column in merged_df.columns:
        def convert_to_object(value):
            try:
                bounds = value.split(',')
                lower_bound = float(bounds[0].split(': ')[1])
                upper_bound = float(bounds[1].split(': ')[1])
                return {
                    'lower_bound': lower_bound,
                    'upper_bound': upper_bound,
                    'average': (lower_bound + upper_bound) / 2
                }
            except (IndexError, ValueError):
                return None

        merged_df[column] = merged_df[column].apply(
            lambda x: convert_to_object(x) if isinstance(x, str) else None
        )

process_bounds_column('impressions')
process_bounds_column('spend')

# Save the final enriched data to JSON
output_enriched_json_path = "final_enriched_meta_ad_data.json"
merged_df.to_json(output_enriched_json_path, orient='records', indent=4)