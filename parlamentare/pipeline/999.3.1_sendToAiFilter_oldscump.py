import glob
import os
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
import anthropic
import sys
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading
import logging
import base64
from pathlib import Path

# Constants
NUM_THREADS = 8
output_path = 'ai/analysis'
images_path = 'downloaded_images'


@dataclass
class ProcessingStats:
    successful: int = 0
    failed: int = 0
    skipped: int = 0


# Thread-safe counter using Lock
stats = ProcessingStats()
stats_lock = threading.Lock()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('meta_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def update_stats(success: bool, skipped: bool = False):
    """Thread-safe update of processing statistics"""
    with stats_lock:
        if skipped:
            stats.skipped += 1
        elif success:
            stats.successful += 1
        else:
            stats.failed += 1


def find_and_encode_image(ad_id: str) -> Optional[str]:
    """Find and encode image for an ad"""
    # Check for both resized and original versions
    possible_extensions = ['.jpg', '.jpeg']
    possible_types = ['resized', 'original']

    for img_type in possible_types:
        for ext in possible_extensions:
            filename = f"{ad_id}_{img_type}{ext}"
            filepath = os.path.join(images_path, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'rb') as img_file:
                        return base64.b64encode(img_file.read()).decode('utf-8')
                except Exception as e:
                    logger.error(f"Error encoding image {filepath}: {str(e)}")
                    return None
    return None


def format_content(ad_data: Dict[str, Any], user_prompt_template: str) -> List[Dict[str, Any]]:
    """Format content in the required message structure using the template"""
    messages = []

    # Process the data
    processed_data = ad_data.copy()
    processed_data.pop('demographic_distribution', None)
    processed_data.pop('delivery_by_region', None)

    # Format data as key-value pairs
    formatted_content = "# Post Info:\n"
    for key, value in processed_data.items():
        formatted_content += f"## {key}:\n```\n{value}\n```\n"

    # Split the template into sections
    parts = user_prompt_template.split('%document-data%')
    if len(parts) != 2:
        raise ValueError("Template must contain %document-data% placeholder")

    image_parts = parts[1].split('%image-data%')
    if len(image_parts) != 2:
        raise ValueError("Template must contain %image-data% placeholder")

    # Create the first message with post content
    post_section = parts[0] + formatted_content + image_parts[0]
    messages.append({
        "type": "text",
        "text": post_section
    })

    # Add image if available
    encoded_image = find_and_encode_image(ad_data['ad_archive_id'])
    if encoded_image:
        messages.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": encoded_image
            }
        })

    # Add the final section
    messages.append({
        "type": "text",
        "text": image_parts[1]
    })

    return messages


def process_single_ad(ad_data: Dict[str, Any], system_prompt: str, user_prompt_template: str, api_key: str) -> bool:
    """Process a single ad and generate AI analysis"""
    # Check if already processed
    output_filename = f"ad_{ad_data['ad_archive_id']}.xml"
    if os.path.exists(os.path.join(output_path, output_filename)):
        logger.info(f"Skipping ad {ad_data['ad_archive_id']} as it has already been processed")
        update_stats(success=True, skipped=True)
        return True

    try:
        # Format content using the template
        messages = format_content(ad_data, user_prompt_template)

        # Initialize the Anthropic client (thread-safe)
        client = anthropic.Anthropic(api_key=api_key)

        # Send to Claude-3.5-Sonnet
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=4000,
            system=system_prompt,
            messages=[
                {"role": "user", "content": messages}
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

        logger.info(f"Successfully processed ad {ad_data['ad_archive_id']}")
        update_stats(success=True)
        return True

    except Exception as e:
        logger.error(f"Error processing ad {ad_data['ad_archive_id']}: {str(e)}")
        update_stats(success=False)
        return False


def read_prompt(file_path: str) -> str:
    """Read prompt content from file"""
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()


def process_ads(json_file_path: str, api_key: str, max_ads: int = None):
    """Process all ads from the JSON file using multiple threads"""
    # Create output directory
    os.makedirs(output_path, exist_ok=True)

    # Read prompts
    system_prompt = read_prompt('ai/prompts/grader/system-prompt.txt')
    user_prompt_template = read_prompt('ai/prompts/grader/user-prompt.txt')

    # Read JSON file
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
        # Extract ads array from the JSON structure
        ads_data = data.get('ads', [])
        if not ads_data:
            logger.error("No ads found in the JSON file")
            return

    # Limit number of ads if specified
    if max_ads:
        ads_data = ads_data[:max_ads]

    logger.info(f"Starting processing of {len(ads_data)} ads with {NUM_THREADS} threads...")

    # Process ads using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
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

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"Unexpected error in thread: {str(e)}")
                update_stats(success=False)

    # Print final statistics
    logger.info("\nProcessing complete:")
    logger.info(f"Successfully processed: {stats.successful} ads")
    logger.info(f"Failed to process: {stats.failed} ads")
    logger.info(f"Skipped (already processed): {stats.skipped} ads")
    logger.info(f"Total processed: {stats.successful + stats.failed + stats.skipped} ads")


def get_latest_results_file(results_dir: str = "results") -> str:
    """Find the latest fb_ads_results file, excluding test files"""
    # Pattern matches fb_ads_results_ followed by timestamp .json
    pattern = os.path.join(results_dir, "fb_ads_results_[0-9]*.json")
    files = glob.glob(pattern)

    if not files:
        raise FileNotFoundError("No results files found")

    # Sort by modification time and get the latest
    latest_file = max(files, key=os.path.getmtime)
    return latest_file



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <api_key>")
        sys.exit(1)

    api_key = sys.argv[1]
    json_file_path = get_latest_results_file()

    print("Processing ads from:", json_file_path)

    max_ads = None

    process_ads(json_file_path, api_key, max_ads)