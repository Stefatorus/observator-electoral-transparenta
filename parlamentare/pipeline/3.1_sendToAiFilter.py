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
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import magic

# Constants
NUM_THREADS = 32
output_path = 'ai/analysis'
images_path = 'downloaded_images'
GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-002:generateContent"
BASE_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"


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


@retry(wait=wait_exponential(multiplier=1, min=4, max=10),
       stop=stop_after_attempt(3))
def upload_file_to_gemini(file_path: str) -> str:
    """Upload a file using Google's resumable upload protocol."""
    try:
        mime = magic.Magic(mime=True)
        mime_type = mime.from_file(str(file_path))
        file_size = Path(file_path).stat().st_size

        headers = {
            'X-Goog-Upload-Protocol': 'resumable',
            'X-Goog-Upload-Command': 'start',
            'X-Goog-Upload-Header-Content-Length': str(file_size),
            'X-Goog-Upload-Header-Content-Type': mime_type,
            'Content-Type': 'application/json'
        }

        metadata = {
            'file': {
                'display_name': Path(file_path).name
            }
        }

        response = requests.post(
            f"{BASE_URL}?key={api_key}",
            headers=headers,
            json=metadata
        )
        response.raise_for_status()

        upload_url = response.headers.get('X-Goog-Upload-URL')
        if not upload_url:
            raise ValueError("No upload URL received")

        with open(file_path, 'rb') as f:
            upload_headers = {
                'Content-Length': str(file_size),
                'X-Goog-Upload-Offset': '0',
                'X-Goog-Upload-Command': 'upload, finalize'
            }

            response = requests.post(
                upload_url,
                headers=upload_headers,
                data=f.read()
            )
            response.raise_for_status()

            file_info = response.json()
            file_uri = file_info.get('file', {}).get('uri')

            if not file_uri:
                raise ValueError("No file URI received")

            return file_uri, mime_type

    except Exception as e:
        logger.error(f"Error uploading file {file_path}: {str(e)}")
        raise


def find_image_for_ad(ad_id: str) -> Optional[tuple]:
    """Find and get info for an ad's image"""
    possible_extensions = ['.jpg', '.jpeg']
    possible_types = ['resized', 'original']

    for img_type in possible_types:
        for ext in possible_extensions:
            filename = f"{ad_id}_{img_type}{ext}"
            filepath = os.path.join(images_path, filename)
            if os.path.exists(filepath):
                try:
                    return filepath
                except Exception as e:
                    logger.error(f"Error processing image {filepath}: {str(e)}")
                    return None
    return None


def format_content(ad_data: Dict[str, Any], user_prompt_template: str) -> List[Dict[str, Any]]:
    """Format content in the required message structure"""
    processed_data = ad_data.copy()
    processed_data.pop('demographic_distribution', None)
    processed_data.pop('delivery_by_region', None)

    # Format data as key-value pairs
    formatted_content = "# Post Info:\n"
    for key, value in processed_data.items():
        formatted_content += f"## {key}:\n```\n{json.dumps(value)}\n```\n"

    # Split the template into sections
    parts = user_prompt_template.split('%document-data%')
    if len(parts) != 2:
        raise ValueError("Template must contain %document-data% placeholder")

    image_parts = parts[1].split('%image-data%')
    if len(image_parts) != 2:
        raise ValueError("Template must contain %image-data% placeholder")

    contents = []

    # First, add the image content if available
    image_path = find_image_for_ad(ad_data['ad_archive_id'])
    if image_path:
        file_uri, mime_type = upload_file_to_gemini(image_path)
        contents.append({
            "role": "user",
            "parts": [{
                "fileData": {
                    "fileUri": file_uri,
                    "mimeType": mime_type
                }
            }]
        })

    # Then add the text content
    full_prompt = parts[0] + formatted_content + image_parts[0]
    if image_path:
        full_prompt += f"[Image URI: {file_uri}]"
    full_prompt += image_parts[1]

    contents.append({
        "role": "user",
        "parts": [{
            "text": full_prompt
        }]
    })

    return contents


def process_single_ad(ad_data: Dict[str, Any], system_prompt: str, user_prompt_template: str, api_key: str) -> bool:
    """Process a single ad and generate AI analysis"""
    output_filename = f"ad_{ad_data['ad_archive_id']}.json"
    if os.path.exists(os.path.join(output_path, output_filename)):
        logger.info(f"Skipping ad {ad_data['ad_archive_id']} as it has already been processed")
        update_stats(success=True, skipped=True)
        return True

    try:
        # Format content for Gemini API
        contents = format_content(ad_data, user_prompt_template)

        # Create the API request payload
        payload = {
            "contents": contents,
            "systemInstruction": {
                "role": "user",
                "parts": [
                    {
                        "text": system_prompt
                    }
                ]
            },
            "generationConfig": {
                "temperature": 0,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 8192,
                "responseMimeType": "text/plain"
            }
        }

        response = requests.post(
            f"{GENERATE_URL}?key={api_key}",
            headers={'Content-Type': 'application/json'},
            json=payload
        )
        response.raise_for_status()

        result = response.json()

        # Save the output
        output_file_path = os.path.join(output_path, output_filename)
        with stats_lock:
            with open(output_file_path, 'w', encoding='utf-8') as file:
                json.dump(result, file, indent=2)

        logger.info(f"Successfully processed ad {ad_data['ad_archive_id']}")
        update_stats(success=True)
        return True

    except Exception as e:
        logger.error(f"Error processing ad {ad_data['ad_archive_id']}: {str(e)}")
        if hasattr(response, 'text'):
            logger.error(f"Response text: {response.text}")
        update_stats(success=False)
        return False


def read_prompt(file_path: str) -> str:
    """Read prompt content from file"""
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()


def get_latest_results_file(results_dir: str = "results") -> str:
    """Find the latest fb_ads_results file, excluding test files"""
    pattern = os.path.join(results_dir, "fb_ads_results_[0-9]*.json")
    files = glob.glob(pattern)

    if not files:
        raise FileNotFoundError("No results files found")

    return max(files, key=os.path.getmtime)


def process_ads(json_file_path: str, api_key: str, max_ads: int = None):
    """Process all ads from the JSON file using multiple threads"""
    os.makedirs(output_path, exist_ok=True)

    system_prompt = read_prompt('ai/prompts/grader/system-prompt.txt')
    user_prompt_template = read_prompt('ai/prompts/grader/user-prompt.txt')

    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
        ads_data = data.get('ads', [])
        if not ads_data:
            logger.error("No ads found in the JSON file")
            return

    if max_ads:
        ads_data = ads_data[:max_ads]

    logger.info(f"Starting processing of {len(ads_data)} ads with {NUM_THREADS} threads...")

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

    logger.info("\nProcessing complete:")
    logger.info(f"Successfully processed: {stats.successful} ads")
    logger.info(f"Failed to process: {stats.failed} ads")
    logger.info(f"Skipped (already processed): {stats.skipped} ads")
    logger.info(f"Total processed: {stats.successful + stats.failed + stats.skipped} ads")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <api_key>")
        sys.exit(1)

    api_key = sys.argv[1]
    try:
        json_file_path = get_latest_results_file()
        print("Processing ads from:", json_file_path)
        process_ads(json_file_path, api_key)
    except FileNotFoundError as e:
        logger.error(f"Error finding results file: {str(e)}")
        sys.exit(1)