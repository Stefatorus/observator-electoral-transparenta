import os
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
import anthropic
import sys
from typing import Dict, Any, List
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading

# Constants
NUM_THREADS = 8
output_path = 'ai/analysis'


@dataclass
class ProcessingStats:
    successful: int = 0
    failed: int = 0
    skipped: int = 0


# Thread-safe counter using Lock
stats = ProcessingStats()
stats_lock = threading.Lock()


def update_stats(success: bool, skipped: bool = False):
    """Thread-safe update of processing statistics"""
    with stats_lock:
        if skipped:
            stats.skipped += 1
        elif success:
            stats.successful += 1
        else:
            stats.failed += 1


def process_single_ad(ad_data: Dict[str, Any], system_prompt: str, user_prompt_template: str, api_key: str) -> bool:
    """Process a single ad and generate AI analysis"""
    # Check if already processed
    output_filename = f"ad_{ad_data['ad_archive_id']}.xml"
    if os.path.exists(os.path.join(output_path, output_filename)):
        print(f"Skipping ad {ad_data['ad_archive_id']} as it has already been processed")
        update_stats(success=True, skipped=True)
        return True

    # Drop irrelevant fields to not overuse tokens
    processed_data = ad_data.copy()
    processed_data.pop('demographic_distribution', None)
    processed_data.pop('delivery_by_region', None)

    # Don't handle ones without a 'ad_creative_bodies'
    if not processed_data['ad_creative_bodies']:
        print(f"Skipping ad {processed_data['ad_archive_id']} as it has no creative")
        update_stats(success=False)
        return False

    # Write it as key: value (on next line) to avoid token overuse
    formatted_content = "# Post Info:\n"
    for key, value in processed_data.items():
        formatted_content += f"## {key}:\n```\n{value}\n```\n"

    user_prompt = user_prompt_template.replace('%document-data%', formatted_content)

    try:
        # Initialize the Anthropic client (thread-safe)
        client = anthropic.Anthropic(api_key=api_key)

        # Send to Claude-3.5-Sonnet
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        # Extract the response content
        ai_output = response.content[0].text

        # Save the output as XML
        output_file_path = os.path.join(output_path, output_filename)

        # Use a lock when writing to the same directory
        with stats_lock:
            with open(output_file_path, 'w', encoding='utf-8') as file:
                file.write(ai_output)

        print(f"Successfully processed ad {ad_data['ad_archive_id']}")
        update_stats(success=True)
        return True

    except Exception as e:
        print(f"Error processing ad {ad_data['ad_archive_id']}: {str(e)}")
        update_stats(success=False)
        return False


def read_prompt(file_path: str) -> str:
    """Read prompt content from file"""
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()


def process_ads(json_file_path: str, api_key: str, max_ads: int = None):
    """Process all ads from the JSON file using multiple threads"""
    # Read prompts
    system_prompt = read_prompt('ai/prompts/grader/system-prompt.txt')
    user_prompt_template = read_prompt('ai/prompts/grader/user-prompt.txt')

    # Create output directory
    os.makedirs(output_path, exist_ok=True)

    # Read JSON file
    with open(json_file_path, 'r', encoding='utf-8') as file:
        ads_data = json.load(file)

    # Limit number of ads if specified
    if max_ads:
        ads_data = ads_data[:max_ads]

    print(f"Starting processing of {len(ads_data)} ads with {NUM_THREADS} threads...")

    # Process ads using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        # Submit all tasks
        futures = [
            executor.submit(
                process_single_ad,
                ad,
                system_prompt,
                user_prompt_template,
                api_key
            )
            for ad in ads_data
        ]

        # Wait for all tasks to complete
        for future in as_completed(futures):
            try:
                future.result()  # This will raise any exceptions that occurred
            except Exception as e:
                print(f"Unexpected error in thread: {str(e)}")
                update_stats(success=False)

    # Print final statistics
    print(f"\nProcessing complete:")
    print(f"Successfully processed: {stats.successful} ads")
    print(f"Failed to process: {stats.failed} ads")
    print(f"Skipped (already processed): {stats.skipped} ads")
    print(f"Total processed: {stats.successful + stats.failed + stats.skipped} ads")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <api_key>")
        sys.exit(1)

    api_key = sys.argv[1]
    json_file_path = 'final_enriched_meta_ad_data.json'
    max_ads = None

    process_ads(json_file_path, api_key, max_ads)