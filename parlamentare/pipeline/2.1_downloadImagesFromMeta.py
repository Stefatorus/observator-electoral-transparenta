#!/usr/bin/env python3
import json
import os
import requests
from urllib.parse import urlparse
from pathlib import Path
import logging
import time
from typing import Dict, List, Optional, Tuple
import glob
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

# Set up logging with thread safety
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('image_downloader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create a lock for thread-safe logging
log_lock = Lock()


class MetaImageDownloader:
    def __init__(self, results_dir: str = "results", output_dir: str = "downloaded_images", num_threads: int = 16):
        """
        Initialize the downloader with input and output directories.

        Args:
            results_dir (str): Directory containing scraper results
            output_dir (str): Directory where images will be saved
            num_threads (int): Number of download threads to use
        """
        self.results_dir = Path(results_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.num_threads = num_threads
        self.session = requests.Session()
        self.download_lock = Lock()

    def get_latest_results_file(self) -> Optional[Path]:
        """
        Get the path to the latest full results file.

        Returns:
            Optional[Path]: Path to the latest results file or None if not found
        """
        pattern = str(self.results_dir / "fb_ads_results_*.json")
        files = glob.glob(pattern)

        if not files:
            return None

        return Path(max(files, key=os.path.getmtime))

    def extract_image_urls(self, ad_data: Dict) -> List[Dict[str, str]]:
        """
        Extract all image URLs from the ad data.

        Args:
            ad_data (Dict): The JSON ad data

        Returns:
            List[Dict[str, str]]: List of dictionaries containing image URLs and types
        """
        images = []

        if "snapshot" in ad_data and "images" in ad_data["snapshot"]:
            for img in ad_data["snapshot"]["images"]:
                if "resized_image_url" in img:
                    images.append({
                        "url": img["resized_image_url"],
                        "type": "resized"
                    })
                elif "original_image_url" in img:
                    images.append({
                        "url": img["original_image_url"],
                        "type": "original"
                    })

        return images

    def get_expected_image_paths(self, ad_data: Dict) -> List[Path]:
        """
        Get the expected file paths for all images of an ad.

        Args:
            ad_data (Dict): The JSON ad data

        Returns:
            List[Path]: List of expected file paths
        """
        image_urls = self.extract_image_urls(ad_data)
        ad_id = ad_data.get("ad_archive_id", "unknown_ad")
        paths = []

        for img_data in image_urls:
            parsed_url = urlparse(img_data["url"])
            ext = os.path.splitext(parsed_url.path)[1]
            if not ext:
                ext = '.jpg'
            filename = f"{ad_id}_{img_data['type']}{ext}"
            paths.append(self.output_dir / filename)

        return paths

    def ad_images_exist(self, ad_data: Dict) -> bool:
        """
        Check if all images for an ad already exist.

        Args:
            ad_data (Dict): The JSON ad data

        Returns:
            bool: True if all images exist, False otherwise
        """
        expected_paths = self.get_expected_image_paths(ad_data)
        return all(path.exists() for path in expected_paths)

    def download_image(self, url: str, image_type: str, ad_id: str) -> Optional[Path]:
        """
        Download an image from a URL.

        Args:
            url (str): The image URL
            image_type (str): Type of image (original, resized, profile)
            ad_id (str): The ad's ID

        Returns:
            Optional[Path]: Path where image was saved, or None if download failed
        """
        try:
            parsed_url = urlparse(url)
            ext = os.path.splitext(parsed_url.path)[1]
            if not ext:
                ext = '.jpg'

            filename = f"{ad_id}_{image_type}{ext}"
            filepath = self.output_dir / filename

            # Thread-safe check for existing file
            with self.download_lock:
                if filepath.exists():
                    with log_lock:
                        logger.debug(f"File already exists, skipping: {filename}")
                    return filepath

                # Download the image
                response = self.session.get(url, timeout=10)
                response.raise_for_status()

                # Save the image
                with open(filepath, 'wb') as f:
                    f.write(response.content)

                with log_lock:
                    logger.info(f"Successfully downloaded: {filename}")
                return filepath

        except requests.exceptions.RequestException as e:
            with log_lock:
                logger.error(f"Failed to download image from {url}: {str(e)}")
            return None
        except Exception as e:
            with log_lock:
                logger.error(f"Error saving image from {url}: {str(e)}")
            return None

    def download_worker(self, task: Tuple[str, str, str]) -> Optional[Path]:
        """
        Worker function for thread pool.

        Args:
            task (Tuple[str, str, str]): Tuple of (url, image_type, ad_id)

        Returns:
            Optional[Path]: Path where image was saved, or None if download failed
        """
        url, image_type, ad_id = task
        return self.download_image(url, image_type, ad_id)

    def process_ad(self, ad_data: Dict) -> List[Path]:
        """
        Process a single ad and download all its images using thread pool.

        Args:
            ad_data (Dict): The JSON ad data

        Returns:
            List[Path]: List of paths to downloaded images
        """
        if self.ad_images_exist(ad_data):
            ad_id = ad_data.get("ad_archive_id", "unknown_ad")
            with log_lock:
                logger.info(f"Skipping ad {ad_id} - all images already exist")
            return self.get_expected_image_paths(ad_data)

        downloaded_files = []
        image_urls = self.extract_image_urls(ad_data)
        ad_id = ad_data.get("ad_archive_id", "unknown_ad")

        # Create download tasks
        tasks = [(img_data["url"], img_data["type"], ad_id) for img_data in image_urls]

        # Use thread pool for downloads
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            results = list(executor.map(self.download_worker, tasks))
            downloaded_files.extend([r for r in results if r is not None])

        return downloaded_files


def main():
    """Main function to run the image downloader."""
    try:
        # Initialize downloader with 16 threads
        downloader = MetaImageDownloader(num_threads=16)

        # Get latest results file
        results_file = downloader.get_latest_results_file()
        if not results_file:
            logger.error("No results files found in the results directory")
            return

        logger.info(f"Processing results file: {results_file}")

        # Read JSON file
        with open(results_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Process ads from the results
        total_downloads = 0
        new_downloads = 0
        ads_data = data.get("ads", [])

        logger.info(f"Found {len(ads_data)} ads to process")
        start_time = time.time()

        # Process ads with thread pool
        with ThreadPoolExecutor(max_workers=16) as executor:
            # Submit all ads for processing
            future_to_ad = {executor.submit(downloader.process_ad, ad): ad for ad in ads_data}

            # Process completed downloads
            for future in concurrent.futures.as_completed(future_to_ad):
                try:
                    downloaded = future.result()
                    total_downloads += len(downloaded)
                    # Count only newly downloaded files
                    new_downloads += sum(1 for path in downloaded if path.stat().st_mtime > start_time)
                except Exception as e:
                    logger.error(f"Error processing ad: {str(e)}")

        elapsed_time = time.time() - start_time
        logger.info(f"Process complete in {elapsed_time:.2f} seconds.")
        logger.info(f"Total images: {total_downloads}, Newly downloaded: {new_downloads}")

    except FileNotFoundError:
        logger.error("Results directory or file not found")
    except json.JSONDecodeError:
        logger.error("Invalid JSON format in results file")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")


if __name__ == "__main__":
    main()