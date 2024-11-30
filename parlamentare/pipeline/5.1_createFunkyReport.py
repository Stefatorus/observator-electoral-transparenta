import os
import re
import json
from typing import Optional, Tuple, Dict
import pandas as pd


def extract_complaint_info(json_content: Dict) -> Optional[Tuple[str, str, str]]:
    """Extract entity, violation and ad_archive_id from the JSON response"""
    try:
        output = json_content.get('candidates', [])[0].get('content', {}).get('parts', [])[0].get('text', '')

        message_pattern = r"<message-for-police>(.*?)<\/message-for-police>"
        entity_pattern = r"<responsible-party-or-group>(.*?)<\/responsible-party-or-group>"

        message_match = re.search(message_pattern, output, re.DOTALL)
        entity_match = re.search(entity_pattern, output, re.DOTALL)

        if message_match and entity_match:
            message = message_match.group(1).strip()
            entity = entity_match.group(1).strip()
            return entity, message

        return None
    except Exception as e:
        print(f"Error extracting complaint info: {str(e)}")
        return None


def parse_complaint(message: str) -> Tuple[str, str]:
    """Parse the complaint message to extract violation details"""
    if not message:
        return "", ""

    parts = message.split(', pentru incalcarea articolului 98 t) din LEGEA nr. 208 din 20 iulie 2015, prin', 1)
    if len(parts) == 2:
        parts[1] = parts[1].replace("23.11.2024", "30.11.2024")
        return parts[0].strip(), parts[1].strip()
    return "", message


def create_excel_report(input_dir: str, output_dir: str, fb_ads_file: str):
    """Create Excel report from JSON files and Facebook Ads data"""
    if not os.path.exists(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist!")
        return

    # Load Facebook Ads data
    try:
        with open(fb_ads_file, 'r', encoding='utf-8') as f:
            fb_ads_data = json.load(f)
            # Create a lookup dictionary by ad_archive_id
            ads_lookup = {ad['ad_archive_id']: ad for ad in fb_ads_data.get('ads', [])}
    except Exception as e:
        print(f"Error loading Facebook Ads data: {str(e)}")
        return

    # Initialize lists to store data
    report_data = []

    # Process all JSON files
    json_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]
    print(f"Found {len(json_files)} JSON files in the input directory.")

    for filename in json_files:
        file_path = os.path.join(input_dir, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)

            complaint_info = extract_complaint_info(content)
            if complaint_info:
                entity, message = complaint_info

                ad_archive_id = filename.split('_')[1].split('.')[0]

                if message and ad_archive_id:
                    _, violation = parse_complaint(message)
                    if violation:
                        # Get additional ad information from the ads lookup
                        ad_data = ads_lookup.get(ad_archive_id, {})
                        if ad_data:
                            page_id = ad_data.get('page_id', '')

                            report_entry = {
                                "page link": f"https://www.facebook.com/{page_id}" if page_id else '',
                                "page name": ad_data.get('page_name', ''),
                                "ads link": f"https://www.facebook.com/ads/library/?id={ad_archive_id}",
                                "ad spend": ad_data.get('spend', ''),
                                "ad impressions": ad_data.get('impressions_with_index', {}).get('impressions_text', ''),
                                "ad start date": ad_data.get('start_date', ''),
                                "ad end date": ad_data.get('end_date', ''),
                                "summary": violation
                            }

                            report_data.append(report_entry)

        except Exception as e:
            print(f"Error processing {filename}: {str(e)}")

    print("Finished processing all JSON files.")
    print("Total violations found:", len(report_data))

    if report_data:
        try:
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, 'funky_report.xlsx')

            # Create DataFrame and save to Excel
            df = pd.DataFrame(report_data)

            # Reorder columns
            columns_order = [
                "page name",
                "page link",
                "ads link",
                "ad spend",
                "ad impressions",
                "ad start date",
                "ad end date",
                "summary"
            ]

            df = df[columns_order]

            # Write to Excel with some formatting
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Report')

                # Auto-adjust columns width
                worksheet = writer.sheets['Report']
                for idx, col in enumerate(df.columns):
                    max_length = max(df[col].astype(str).apply(len).max(), len(col))
                    worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 100)

            print(f"Report generated: {output_file}")
        except Exception as e:
            print(f"Error creating Excel report: {str(e)}")
    else:
        print("No valid violations found in any JSON files.")


if __name__ == "__main__":
    input_dir = os.path.join('ai', 'analysis')
    output_dir = os.path.join('rapoarte')
    fb_ads_file = os.path.join('results', 'fb_ads_results_20241130_162320.json')

    create_excel_report(input_dir, output_dir, fb_ads_file)