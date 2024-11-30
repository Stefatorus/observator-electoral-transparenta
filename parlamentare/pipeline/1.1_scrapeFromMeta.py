import json
import sys
import requests
import time
from datetime import datetime
import logging
from typing import Dict, List, Any
import os
from pathlib import Path


class FacebookAdsScraper:
    def __init__(self, api_token: str):
        self.api_base = "https://api.apify.com/v2/acts/curious_coder~facebook-ads-library-scraper"
        self.api_token = api_token
        self.setup_logging()

    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('fb_ads_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def load_meta_config(self, meta_file: str) -> Dict:
        """Load the meta configuration from JSON file"""
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading meta configuration: {e}")
            raise

    def start_run(self, config: Dict) -> str:
        """Start an async run and return the run ID"""
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }

        try:
            self.logger.info("Starting async run")
            response = requests.post(
                f"{self.api_base}/runs",
                headers=headers,
                json=config,
                timeout=60
            )
            response.raise_for_status()
            run_data = response.json()
            return run_data['data']['id']
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to start run: {e}")
            raise

    def wait_for_run(self, run_id: str, check_interval: int = 30) -> List[Dict]:
        """Wait for run completion and return results"""
        headers = {
            'Authorization': f'Bearer {self.api_token}'
        }

        while True:
            try:
                # Check run status
                status_response = requests.get(
                    f"{self.api_base}/runs/{run_id}",
                    headers=headers
                )
                status_response.raise_for_status()
                status_data = status_response.json()

                status = status_data['data']['status']
                self.logger.info(f"Run status: {status}")

                if status == 'SUCCEEDED':
                    # Get dataset items
                    items_response = requests.get(
                        f"{self.api_base}/runs/last/dataset/items",
                        headers=headers
                    )
                    items_response.raise_for_status()
                    return items_response.json()
                elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                    raise Exception(f"Run failed with status: {status}")

                time.sleep(check_interval)

            except requests.exceptions.RequestException as e:
                self.logger.error(f"API request failed: {e}")
                raise

    def process_results(self, results: List[Dict]) -> Dict[str, Any]:

        # Remove duplicates (by ad_archive_id. If it doesn't exist, we drop it)
        # We will use a set to keep track of the ad_archive_id's we have seen
        seen_ids = set()
        unique_results = []

        for ad in results:
            ad_id = ad.get('ad_archive_id')
            if ad_id and ad_id not in seen_ids:
                unique_results.append(ad)
                seen_ids.add(ad_id)

        self.logger.info(f"Removed {len(results) - len(unique_results)} duplicate ads")

        results = unique_results


        """Process and organize the results"""
        processed_data = {
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "total_ads": len(results),
                "query_count": len(set(ad.get('query', '') for ad in results))
            },
            "ads": results,
            "summary": {
                "by_query": {},
                "by_page": {},
                "by_date": {}
            }
        }

        # Generate summaries
        for ad in results:
            # Summary by query
            query = ad.get('query', 'unknown')
            if query not in processed_data["summary"]["by_query"]:
                processed_data["summary"]["by_query"][query] = 0
            processed_data["summary"]["by_query"][query] += 1

            # Summary by page
            page = ad.get('page_name', 'unknown')
            if page not in processed_data["summary"]["by_page"]:
                processed_data["summary"]["by_page"][page] = 0
            processed_data["summary"]["by_page"][page] += 1

            # Summary by date
            start_date = ad.get('ad_creation_time', '').split('T')[0]
            if start_date:
                if start_date not in processed_data["summary"]["by_date"]:
                    processed_data["summary"]["by_date"][start_date] = 0
                processed_data["summary"]["by_date"][start_date] += 1

        return processed_data

    def save_results(self, results: Dict, output_dir: str = "results"):
        """Save the results to JSON files"""
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        # Save full results
        full_path = os.path.join(output_dir, f"fb_ads_results_{timestamp}.json")
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # Save summary separately
        summary_path = os.path.join(output_dir, f"fb_ads_summary_{timestamp}.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(results["summary"], f, ensure_ascii=False, indent=2)

        self.logger.info(f"Results saved to {full_path}")
        self.logger.info(f"Summary saved to {summary_path}")


def main():
    # Check for API token
    if len(sys.argv) < 2:
        print("Usage: python 1.1_scrapeFromMeta.py <API_TOKEN>")
        sys.exit(1)

    # Get API token from argv
    api_token = sys.argv[1]

    # Initialize scraper
    scraper = FacebookAdsScraper(api_token)

    try:
        # Load configuration
        config = scraper.load_meta_config('requests/meta.json')

        # Start async run
        run_id = scraper.start_run(config)
        print(f"Started run with ID: {run_id}")

        # Wait for results
        print("Waiting for run to complete...")
        raw_results = scraper.wait_for_run(run_id)

        # Process results
        processed_results = scraper.process_results(raw_results)

        # Save results
        scraper.save_results(processed_results)

        print("Scraping completed successfully!")

    except Exception as e:
        scraper.logger.error(f"Error during scraping: {e}")
        raise


if __name__ == "__main__":
    main()