import json
import matplotlib.pyplot as plt
import pandas as pd
import os

# Create the output directory for graphs
output_dir = "graphs"
os.makedirs(output_dir, exist_ok=True)

# Load JSON data
input_json_file = "final_enriched_meta_ad_data.json"  # Replace with your JSON file name
with open(input_json_file, 'r') as f:
    data = json.load(f)


# Get date of modified of the JSON


# Convert to DataFrame for easier processing
df = pd.DataFrame(data)

df['ad_delivery_start_time'] = pd.to_datetime(df['ad_delivery_start_time'], errors='coerce')
df['ad_delivery_days'] = (pd.to_datetime('today') - df['ad_delivery_start_time']).dt.days + 1

# Process impressions and spend into averages if not already done
if 'impressions' in df.columns:
    df['impressions_avg'] = df['impressions'].apply(
        lambda x: x['average'] if isinstance(x, dict) and 'average' in x else None
    )

    # Check impressions after deadline
    df['impressions_after_deadline'] = df['impressions_avg'] / df['ad_delivery_days'] / 24 * 6


if 'spend' in df.columns:
    df['spend_avg'] = df['spend'].apply(
        lambda x: x['average'] if isinstance(x, dict) and 'average' in x else None
    )

    df['spend_after_deadline'] = df['spend_avg'] / df['ad_delivery_days'] / 24 * 6

# 1. Plot total spend by page name
spend_by_page = df.groupby('page_name')['spend_after_deadline'].sum().sort_values(ascending=False)

# 2. Plot total impressions by page name
impressions_by_page = df.groupby('page_name')['impressions_after_deadline'].sum().sort_values(ascending=False)

# Only take top 50, very wide plots
spend_by_page = spend_by_page.head(50)
impressions_by_page = impressions_by_page.head(50)


# Save the plots
spend_by_page.plot(kind='bar', title='Total Spend by Page Name')
plt.ylabel('Spend')
plt.xlabel('Page Name')
plt.tight_layout()
plt.savefig(f"{output_dir}/total_spend_by_page.png")
plt.close()

impressions_by_page.plot(kind='bar', title='Total Impressions by Page Name')
plt.ylabel('Impressions')
plt.xlabel('Page Name')
plt.tight_layout()
plt.savefig(f"{output_dir}/total_impressions_by_page.png")
plt.close()


print(f"Graphs saved in the '{output_dir}' folder.")
