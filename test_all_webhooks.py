#!/usr/bin/env python3
"""Test all 4 webhook types against extraction functions"""

import sys
import os

# Change to script directory
os.chdir('/etc/openhab/hikvision-analytics')

# Import extraction functions from webhook_processor
from webhook_processor import (
    extract_analytics_from_webhook_bytes,
    extract_linedetection_from_xml
)

print("="*80)
print("TESTING ALL 4 WEBHOOK TYPES")
print("="*80)

tests = [
    ('1. Camera 2 Line Crossing (XML)', 'webhook_20260209_180557.txt'),
    ('2. Camera 1 Heartbeat (TrackInfo)', 'webhook_20260209_180600.txt'),
    ('3. Camera 1 PersonArmingTrack (NEW)', 'webhook_20260209_180636.txt'),
    ('4. Camera 1 CaptureResult (OLD)', 'webhook_20260209_220001.txt')
]

for name, fname in tests:
    print(f"\n{'='*80}")
    print(f"{name}")
    print(f"File: {fname}")
    print('='*80)
    
    with open(fname, 'r', errors='ignore') as f:
        content_text = f.read()
    with open(fname, 'rb') as f:
        content_bytes = f.read()
    
    # Check webhook type
    if 'linedetection' in content_text or '<eventType>linedetection</eventType>' in content_text:
        print("Type: LINE CROSSING (Camera 2)")
        linedata, jpeg_image = extract_linedetection_from_xml(content_text, content_bytes)
        if linedata:
            print(f"✅ Extraction SUCCESS")
            print(f"  - Target: {linedata.get('targetType', 'unknown')}")
            print(f"  - Direction: {linedata.get('direction', 'unknown')}")
            print(f"  - RegionID: {linedata.get('regionID', 'unknown')}")
            print(f"  - Image: {len(jpeg_image) if jpeg_image else 0} bytes")
        else:
            print("❌ Extraction FAILED")
    else:
        print("Type: BODY DETECTION (Camera 1)")
        analytics, background_image = extract_analytics_from_webhook_bytes(content_text, content_bytes)
        if analytics:
            print(f"✅ Extraction SUCCESS - {len(analytics)} fields")
            for key, value in sorted(analytics.items()):
                if not key.endswith('snapTime'):
                    print(f"  - {key}: {value}")
            print(f"  - Image: {len(background_image) if background_image else 0} bytes")
        else:
            print("⚠️  No analytics (heartbeat or empty)")

print(f"\n{'='*80}")
print("TEST COMPLETE")
print("="*80)
