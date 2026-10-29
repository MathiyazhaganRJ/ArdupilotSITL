#!/usr/bin/env python3
"""
Pre-download Satellite Map Tiles for Offline Flight Testing
===========================================================
Downloads and caches high-resolution satellite tiles for a designated
flight test area to disk so the 3D Visualizer can operate 100% offline
in remote field locations with zero internet connection.

Usage:
    python tools/predownload_map.py --lat 8.3105 --lon 77.3137 --radius 3.0 --zoom 18
"""

import os
import sys
import math
import argparse
import urllib.request
import concurrent.futures
import time
import re

def lon2tile(lon, zoom):
    return (lon + 180.0) / 360.0 * (2 ** zoom)

def lat2tile(lat, zoom):
    rad = math.radians(lat)
    return (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * (2 ** zoom)

def get_tiles_for_radius(lat, lon, radius_km, zoom):
    # Earth radius ~ 6,371 km
    lat_delta = (radius_km / 6371.0) * (180.0 / math.pi)
    lon_delta = (radius_km / (6371.0 * math.cos(math.radians(lat)))) * (180.0 / math.pi)

    min_x = int(lon2tile(lon - lon_delta, zoom))
    max_x = int(lon2tile(lon + lon_delta, zoom))
    min_y = int(lat2tile(lat + lat_delta, zoom))
    max_y = int(lat2tile(lat - lat_delta, zoom))

    tiles = []
    for x in range(min(min_x, max_x), max(min_x, max_x) + 1):
        for y in range(min(min_y, max_y), max(min_y, max_y) + 1):
            tiles.append((zoom, x, y))
    return tiles

def download_tile(tile_info, cache_dir):
    zoom, x, y = tile_info
    tile_filename = os.path.join(cache_dir, f"{zoom}_{x}_{y}.jpg")

    # If already cached and valid, skip download
    if os.path.exists(tile_filename) and os.path.getsize(tile_filename) > 100:
        return 'CACHED', os.path.getsize(tile_filename)

    # Cycle across Google's 4 tile servers
    mt = abs(x + y) % 4
    url = f"https://mt{mt}.google.com/vt/lyrs=s&x={x}&y={y}&z={zoom}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 100:
                        with open(tile_filename, 'wb') as f:
                            f.write(data)
                        return 'DOWNLOADED', len(data)
        except Exception:
            time.sleep(0.3)

    return 'FAILED', 0

def main():
    parser = argparse.ArgumentParser(description="Pre-download map tiles for offline flight testing")
    parser.add_argument("--lat", type=float, default=8.3105, help="Center latitude of flight test range (e.g. 8.3105)")
    parser.add_argument("--lon", type=float, default=77.3137, help="Center longitude of flight test range (e.g. 77.3137)")
    parser.add_argument("--radius", type=float, default=3.0, help="Airspace radius in kilometers (default: 3.0 km)")
    parser.add_argument("--zoom", type=str, default="18", help="Zoom level(s), e.g. 18 or 17,18 (default: 18)")
    parser.add_argument("--preset", type=str, default=None, help="Airfield preset name (creates dedicated subfolder inside tile_cache)")
    parser.add_argument("--output", type=str, default=None, help="Directory to save tile cache")
    parser.add_argument("--workers", type=int, default=12, help="Parallel download threads (default: 12)")
    args = parser.parse_args()

    # Determine cache directory
    if args.output:
        cache_dir = os.path.abspath(args.output)
    else:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if args.preset:
            clean_preset = re.sub(r'[^a-zA-Z0-9_\-]+', '_', args.preset.strip()).strip('_')
            cache_dir = os.path.join(root_dir, "tile_cache", clean_preset)
        else:
            cache_dir = os.path.join(root_dir, "tile_cache")

    os.makedirs(cache_dir, exist_ok=True)

    zoom_levels = [int(z.strip()) for z in args.zoom.split(',') if z.strip().isdigit()]
    if not zoom_levels:
        zoom_levels = [18]

    all_tiles = []
    for z in zoom_levels:
        tiles = get_tiles_for_radius(args.lat, args.lon, args.radius, z)
        all_tiles.extend(tiles)

    total = len(all_tiles)
    print("\n" + "=" * 65)
    print("   OFFLINE SATELLITE MAP PRE-DOWNLOADER FOR FLIGHT TESTING")
    print("=" * 65)
    print(f" Test Airspace Center : {args.lat:.5f}°, {args.lon:.5f}°")
    print(f" Airspace Radius      : {args.radius:.1f} km ({args.radius * 2:.1f} km diameter)")
    print(f" Zoom Level(s)        : {zoom_levels}")
    print(f" Total Target Tiles   : {total} tiles")
    print(f" Cache Destination    : {cache_dir}")
    print("=" * 65 + "\n")

    downloaded = 0
    cached = 0
    failed = 0
    total_bytes = 0

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_tile = {executor.submit(download_tile, tile, cache_dir): tile for tile in all_tiles}
        for idx, future in enumerate(concurrent.futures.as_completed(future_to_tile), start=1):
            status, size = future.result()
            total_bytes += size
            if status == 'DOWNLOADED':
                downloaded += 1
            elif status == 'CACHED':
                cached += 1
            else:
                failed += 1

            pct = (idx / total) * 100.0
            mb = total_bytes / (1024 * 1024)
            bar_len = 30
            filled = int(bar_len * idx // total)
            bar = '=' * filled + '-' * (bar_len - filled)
            try:
                sys.stdout.write(f"\r[{bar}] {pct:5.1f}% | {idx}/{total} tiles | {mb:5.1f} MB | DL: {downloaded} Cached: {cached} Err: {failed}")
                sys.stdout.flush()
            except Exception:
                pass

    t1 = time.time()
    print("\n\n" + "=" * 65)
    print(f" DOWNLOAD COMPLETE in {t1 - t0:.1f} seconds!")
    print(f" Successfully Ready for Offline Flight: {downloaded + cached}/{total} tiles")
    print(f" Total Cached Data Size: {total_bytes / (1024 * 1024):.2f} MB")
    print(f" Stored at: {cache_dir}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
