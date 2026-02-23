#!/usr/bin/env /etc/openhab/.venv/bin/python3
"""Test PersonArmingTrack extraction with debug logging"""

import sys
import logging

# Set up debug logging BEFORE importing webhook_processor
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')

# Import extraction functions
from webhook_processor import extract_analytics_from_webhook_bytes
import webhook_processor

# Also set the webhook_processor logger to DEBUG
webhook_processor.logger.setLevel(logging.DEBUG)

print("="*80)
print("Testing PersonArm Track webhook with DEBUG logging...")
print("="*80)

with open('webhook_20260209_180636.txt', 'r', errors='ignore') as f:
    content_text = f.read()
with open('webhook_20260209_180636.txt', 'rb') as f:
    content_bytes = f.read()

analytics, image = extract_analytics_from_webhook_bytes(content_text, content_bytes)

print(f"\n{'='*80}")
print(f"Result: {'✅ SUCCESS' if analytics else '❌ FAILED'}")
print("="*80)
if analytics:
    print(f"Extracted {len(analytics)} fields:")
    for key, value in sorted(analytics.items()):
        print(f"  {key}: {value}")
    print(f"\nImage: {len(image) if image else 0} bytes")
else:
    print("No analytics extracted")
