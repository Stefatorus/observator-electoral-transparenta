import random

from TikTokApi import TikTokApi
import asyncio
import os
import json
from datetime import datetime
import pathlib
import traceback
from dotenv import load_dotenv
import time
import aiohttp
from typing import List

from tools.cookies import get_cookies
from tools.proxies import get_proxies

load_dotenv()

VIDEOS_PER_TAG = 30
SLEEP_BETWEEN_TAGS = 1
TAG_FILE_PATH = "scrapers/tags.txt"
BATCH_SIZE = 5  # Number of videos to process in parallel
MAX_RETRIES = 3
RETRY_DELAYS = [5, 10, 20]  # Seconds between retries


async def download_file(url: str, output_path: str, session: aiohttp.ClientSession, retry=0):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                with open(output_path, 'wb') as f:
                    f.write(content)
                return True
            elif response.status != 200 and retry < MAX_RETRIES:
                delay = RETRY_DELAYS[retry]
                print(f"Download failed with status {response.status}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
                return await download_file(url, output_path, session, retry + 1)
    except Exception as e:
        if retry < MAX_RETRIES:
            delay = RETRY_DELAYS[retry]
            print(f"Error downloading {url}: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
            return await download_file(url, output_path, session, retry + 1)
        print(f"Max retries reached for {url}: {e}")
    return False


async def fetch_comments(api: TikTokApi, video_id: str):
    comments = []
    try:
        video = api.video(id=video_id)
        async for comment in video.comments(count=10):
            comments.append(comment.as_dict)
    except Exception as e:
        print(f"Error fetching comments for video {video_id}: {e}")
    return comments


async def save_video_data(video_data: dict, api: TikTokApi, session: aiohttp.ClientSession):
    video_id = video_data['id']

    if not ('claInfo' in video_data['video'] and
            video_data['video']['claInfo'].get('captionInfos') and
            any(cap.get('language') == 'ron-RO' for cap in video_data['video']['claInfo']['captionInfos'])):
        return False

    # Drop any before '1732942800' timestamp - Nov 30, 2024
    if video_data['createTime'] < 1732942800:
        return False

    rom_caption = next(cap for cap in video_data['video']['claInfo']['captionInfos']
                       if cap.get('language') == 'ron-RO')
    subtitle_url = rom_caption['url']

    video_dir = pathlib.Path(f"./videos/{video_id}")
    video_dir.mkdir(parents=True, exist_ok=True)

    # Fetch and add comments to video data
    comments = await fetch_comments(api, video_id)
    video_data['comments'] = comments

    # Save video info with comments
    info_path = video_dir / "video_info.json"
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(video_data, f, indent=2, ensure_ascii=False)

    subtitle_path = video_dir / "subtitles.vtt"
    if not await download_file(subtitle_url, str(subtitle_path), session):
        False

    print(f"Downloaded Romanian subtitles for video {video_id}")

    thumbnail_path = video_dir / "thumbnail.jpg"

    if not await download_file(video_data['video']['cover'], str(thumbnail_path), session):
        print(f"Downloaded thumbnail for video {video_id}")
        return False

    return True


async def process_hashtag(api: TikTokApi, tag: str, session: aiohttp.ClientSession):
    video_count = 0
    current_batch = []

    try:
        hashtag = api.hashtag(name=tag)
        async for video in hashtag.videos(count=VIDEOS_PER_TAG):
            try:
                video_dict = video.as_dict
                current_batch.append(video_dict)

                if len(current_batch) >= BATCH_SIZE:
                    tasks = [save_video_data(v, api, session) for v in current_batch]
                    results = await asyncio.gather(*tasks)
                    video_count += sum(1 for r in results if r)
                    current_batch = []
                    print(f"Processed {video_count} Romanian videos for #{tag}")

            except Exception as e:
                print(f"Error processing video for #{tag}: {e}")
                traceback.print_exc()
                continue

        if current_batch:
            tasks = [save_video_data(v, api, session) for v in current_batch]
            results = await asyncio.gather(*tasks)
            video_count += sum(1 for r in results if r)

    except Exception as e:
        print(f"Error processing hashtag #{tag}: {e}")
        traceback.print_exc()

    print(f"Completed #{tag}: {video_count} Romanian videos")
    return video_count


async def main_scraper():
    hashtags = [tag.strip().lstrip('#') for tag in open(TAG_FILE_PATH, encoding='UTF-8').readlines() if tag.strip()]
    if not hashtags:
        print("No hashtags found")
        return

    total_videos = 0

    try:
        async with TikTokApi() as api:
            cookies = get_cookies()
            await api.create_sessions(
                num_sessions=3,
                sleep_after=3,
                cookies=[cookies],
                #proxies=get_proxies()
            )

            async with aiohttp.ClientSession() as session:
                for i, tag in enumerate(hashtags, 1):
                    print(f"\nProcessing hashtag {i}/{len(hashtags)}: #{tag}")
                    video_count = await process_hashtag(api, tag, session)
                    total_videos += video_count

                    if i < len(hashtags):
                        delay = random.uniform(1, 3)
                        time.sleep(delay)

    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
    finally:
        print(f"\nComplete: {len(hashtags)} hashtags, {total_videos} videos")


def main():
    try:
        asyncio.run(main_scraper())
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()