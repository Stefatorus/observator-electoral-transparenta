from TikTokApi import TikTokApi
import asyncio
import os
import json
from datetime import datetime
import pathlib
from typing import List
from dotenv import load_dotenv
import os
import traceback

from tools.proxies import get_proxies
from tools.cookies import get_cookies

# Load environment variables from .env file
load_dotenv()

# Load tokens from environment
ms_tokens = os.environ.get("COOKIE_TOKEN", "").split(",")
if not ms_tokens or not ms_tokens[0]:
    raise ValueError("COOKIE_TOKEN environment variable is required and must be comma-separated")


async def create_output_directory() -> str:
    """Create timestamped directory for storing results"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_path = pathlib.Path("scraping/trending")
    output_dir = base_path / timestamp

    # Create all necessary directories
    output_dir.mkdir(parents=True, exist_ok=True)

    return str(output_dir)


async def save_video_data(video_data: dict, output_dir: str, index: int):
    """Save individual video data to JSON file"""
    filename = f"video_{index:04d}.json"
    filepath = pathlib.Path(output_dir) / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(video_data, f, indent=2, ensure_ascii=False)


async def trending_videos():
    """Fetch and save trending videos data"""
    output_dir = await create_output_directory()
    print(f"Saving data to: {output_dir}")

    video_count = 0
    max_videos = 100  # Maximum videos to collect

    try:
        async with (TikTokApi() as api):
            api._get_cookies = get_cookies
            # Create sessions using all available tokens
            await api.create_sessions(
                # ms_tokens=ms_tokens,
                # num_sessions=len(ms_tokens),
                sleep_after=3,
                proxies=get_proxies()
            )

            print("Starting video collection...")
            async for video in api.trending.videos():
                if video_count >= max_videos:
                    break

                try:
                    # Get full video information as dictionary
                    video_dict = video.as_dict

                    # Add extra metadata
                    video_dict['collection_timestamp'] = datetime.now().isoformat()

                    # Save to file
                    await save_video_data(video_dict, output_dir, video_count)

                    # Progress update
                    video_count += 1
                    if video_count % 10 == 0:
                        print(f"Processed {video_count} videos...")

                except Exception as e:
                    print(f"Error processing video: {e}")
                    traceback.print_exc()
                    continue

    except Exception as e:
        print(f"Fatal error occurred: {e}")
        # Print stack trace
        traceback.print_exc()

    finally:
        print(f"\nCollection complete. Total videos saved: {video_count}")
        print(f"Data location: {output_dir}")


def main():
    """Main entry point with error handling"""
    try:
        asyncio.run(trending_videos())
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
# See PyCharm help at https://www.jetbrains.com/help/pycharm/
