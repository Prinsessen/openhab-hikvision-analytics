#!/usr/bin/env python3
"""
Hikvision Webhook Analytics Processor
Receives webhook notifications from Hikvision camera and updates OpenHAB items
"""

from flask import Flask, request
import json
import requests
from datetime import datetime
import logging
import os
import glob

# Configuration
OPENHAB_URL = "http://localhost:8080"
WEBHOOK_PORT = 5001
LOG_WEBHOOKS = True  # Set to False to disable webhook logging
WEBHOOK_DIR = "/etc/openhab/hikvision-analytics"
MAX_WEBHOOK_FILES = 50  # Keep only the last 50 webhook files
HTML_OUTPUT_PATH = "/etc/openhab/html"  # Where to save detection images
IMAGE_FILENAME = "hikvision_latest.jpg"  # Output image filename
TIMESTAMP_FILENAME = "hikvision_latest_time.txt"  # Output timestamp filename

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def extract_analytics_from_webhook_bytes(content_text, content_bytes):
    """
    Extract Face and Human analytics AND images from webhook multipart content
    Args:
        content_text: Webhook content as text string (for JSON parsing)
        content_bytes: Webhook content as bytes (for image extraction)
    Returns tuple: (analytics_dict, background_image_bytes)
    """
    try:
        # Find the JSON section by looking for the start of mixedTargetDetection
        json_start = content_text.find('{"ipAddress"') 
        if json_start == -1:
            json_start = content_text.find('{\n\t"ipAddress"')
        if json_start == -1:
            json_start = content_text.find('{\n        "ipAddress"')
        
        if json_start != -1:
            # Find the end of this JSON object
            brace_count = 0
            json_end = -1
            for i in range(json_start, len(content_text)):
                if content_text[i] == '{':
                    brace_count += 1
                elif content_text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            
            if json_end != -1:
                json_str = content_text[json_start:json_end]
                result = json.loads(json_str)
                
                analytics = {}
                
                # Extract camera/event info from top level
                analytics['channelName'] = result.get('channelName', 'unknown')
                analytics['eventType'] = result.get('eventType', 'unknown')
                
                # Extract Face and Human analytics from CaptureResult[0]
                capture_results = result.get('CaptureResult', [])
                if capture_results and len(capture_results) > 0:
                    capture = capture_results[0]
                    
                    # Extract Face analytics
                    if 'Face' in capture:
                        face = capture['Face']
                        for prop in face.get('Property', []):
                            analytics['face_' + prop['description']] = prop['value']
                        analytics['face_snapTime'] = face.get('snapTime', '')
                    
                    # Extract Human analytics
                    if 'Human' in capture:
                        human = capture['Human']
                        for prop in human.get('Property', []):
                            analytics['human_' + prop['description']] = prop['value']
                        analytics['human_snapTime'] = human.get('snapTime', '')
                
                logger.debug(f"Parsed JSON successfully, found {len(analytics)} analytics keys")
                
                # Extract background image from webhook bytes
                background_image = extract_background_image_from_webhook_bytes(content_bytes)
                
                if len(analytics) > 2:  # More than just channel/event
                    return analytics, background_image
        
        logger.warning("Could not find valid JSON in webhook content")
        return None, None
    except Exception as e:
        logger.error(f"Error extracting analytics: {e}", exc_info=True)
        return None, None


def extract_background_image_from_webhook_bytes(content_bytes):
    """
    Extract faceBackgroundImage (high-res full scene) from webhook multipart data
    Args:
        content_bytes: Raw webhook content as bytes
    Returns JPEG bytes if found, None otherwise
    """
    try:
        # Find faceBackgroundImage section in bytes
        marker_pattern = b'Content-Disposition: form-data; name="faceBackgroundImage"'
        marker_idx = content_bytes.find(marker_pattern)
        
        if marker_idx == -1:
            logger.debug("faceBackgroundImage section not found in webhook")
            return None
        
        # Find Content-Type: image/jpeg after the marker
        jpeg_marker_start = content_bytes.find(b'Content-Type: image/jpeg', marker_idx)
        if jpeg_marker_start == -1:
            return None
        
        # JPEG data starts after headers (skip to next blank line)
        blank_line = content_bytes.find(b'\r\n\r\n', jpeg_marker_start)
        if blank_line == -1:
            blank_line = content_bytes.find(b'\n\n', jpeg_marker_start)
        if blank_line == -1:
            return None
        
        jpeg_start = blank_line + 4 if content_bytes[blank_line:blank_line+4] == b'\r\n\r\n' else blank_line + 2
        
        # Find the end of JPEG data (next boundary marker)
        boundary_end = content_bytes.find(b'--boundary', jpeg_start)
        if boundary_end == -1:
            boundary_end = len(content_bytes)
        
        # Extract JPEG data (trim whitespace)
        jpeg_data = content_bytes[jpeg_start:boundary_end].strip()
        
        # Verify it's actually JPEG by checking for JPEG markers
        if not jpeg_data.startswith(b'\xff\xd8'):  # JPEG SOI marker
            logger.warning("Extracted data doesn't start with JPEG marker")
            return None
        
        logger.info(f"✅ Extracted background image from webhook: {len(jpeg_data)} bytes")
        return jpeg_data
        
    except Exception as e:
        logger.error(f"Error extracting background image: {e}")
        return None


def cleanup_old_webhooks():
    """
    Remove old webhook files, keeping only the most recent MAX_WEBHOOK_FILES
    """
    try:
        webhook_files = glob.glob(f"{WEBHOOK_DIR}/webhook_*.txt")
        if len(webhook_files) > MAX_WEBHOOK_FILES:
            # Sort by modification time (oldest first)
            webhook_files.sort(key=os.path.getmtime)
            # Delete oldest files
            files_to_delete = webhook_files[:-MAX_WEBHOOK_FILES]
            for old_file in files_to_delete:
                os.remove(old_file)
                logger.debug(f"Deleted old webhook file: {os.path.basename(old_file)}")
            logger.info(f"Cleaned up {len(files_to_delete)} old webhook files")
    except Exception as e:
        logger.error(f"Error cleaning up webhook files: {e}")


def save_detection_image(jpeg_data, timestamp_str):
    """
    Save detection image and timestamp to HTML folder
    Args:
        jpeg_data: JPEG image bytes
        timestamp_str: Detection timestamp string (HH:MM:SS format)
    """
    try:
        # Save image
        image_path = os.path.join(HTML_OUTPUT_PATH, IMAGE_FILENAME)
        with open(image_path, 'wb') as f:
            f.write(jpeg_data)
        logger.info(f"✅ Saved detection image: {image_path} ({len(jpeg_data)} bytes)")
        
        # Save timestamp (just time part for HTML display)
        time_only = timestamp_str.split()[1] if ' ' in timestamp_str else timestamp_str
        timestamp_path = os.path.join(HTML_OUTPUT_PATH, TIMESTAMP_FILENAME)
        with open(timestamp_path, 'w') as f:
            f.write(time_only)
        logger.debug(f"Saved timestamp: {timestamp_path}")
        
    except Exception as e:
        logger.error(f"Error saving detection image: {e}")


def update_openhab_item(item_name, value):
    """Update a single OpenHAB item via REST API"""
    try:
        url = f"{OPENHAB_URL}/rest/items/{item_name}/state"
        headers = {
            "Content-Type": "text/plain",
            "Accept": "application/json"
        }
        response = requests.put(url, data=str(value), headers=headers, timeout=5)
        
        if response.status_code in [200, 201, 202]:
            logger.debug(f"✓ Updated {item_name} = {value}")
            return True
        else:
            logger.warning(f"Failed to update {item_name}: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error updating {item_name}: {e}")
        return False


def process_analytics(analytics):
    """
    Process analytics dict and update OpenHAB items
    Maps webhook data to OpenHAB item names
    """
    if not analytics:
        logger.warning("No analytics to process")
        return
    
    logger.info("Processing analytics and updating OpenHAB items...")
    
    # Camera/Event info
    channel_name = analytics.get('channelName', 'unknown')
    event_type = analytics.get('eventType', 'unknown')
    update_openhab_item('Hikvision_ChannelName', channel_name)
    update_openhab_item('Hikvision_EventType', event_type)
    
    # Use Human data preferentially (more reliable), fallback to Face
    timestamp = analytics.get('human_snapTime') or analytics.get('face_snapTime', '')
    if timestamp:
        # Format: 2026-02-08T08:29:23+01:00
        try:
            dt = datetime.fromisoformat(timestamp.replace('+01:00', ''))
            formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            update_openhab_item('Hikvision_Timestamp', formatted_time)
        except:
            update_openhab_item('Hikvision_Timestamp', timestamp)
    
    # Clothing
    jacket_color = analytics.get('human_jacketColor', 'unknown')
    trousers_color = analytics.get('human_trousersColor', 'unknown')
    jacket_type = analytics.get('human_jacketType', 'unknown')
    trousers_type = analytics.get('human_trousersType', 'unknown')
    
    update_openhab_item('Hikvision_JacketColor', jacket_color)
    update_openhab_item('Hikvision_TrousersColor', trousers_color)
    update_openhab_item('Hikvision_JacketType', jacket_type)
    update_openhab_item('Hikvision_TrousersType', trousers_type)
    
    # Accessories - convert yes/no to ON/OFF
    hat = analytics.get('human_hat') or analytics.get('face_hat', 'no')
    glasses = analytics.get('human_glass') or analytics.get('face_glass', 'no')
    bag = analytics.get('human_bag', 'no')
    things = analytics.get('human_things', 'no')
    mask = analytics.get('human_mask') or analytics.get('face_mask', 'no')
    
    update_openhab_item('Hikvision_HasHat', 'ON' if hat == 'yes' else 'OFF')
    update_openhab_item('Hikvision_HasGlasses', 'ON' if glasses == 'yes' else 'OFF')
    update_openhab_item('Hikvision_HasBag', 'ON' if bag == 'yes' else 'OFF')
    update_openhab_item('Hikvision_HasThings', 'ON' if things == 'yes' else 'OFF')
    update_openhab_item('Hikvision_HasMask', 'ON' if mask == 'yes' else 'OFF')
    
    # Person attributes
    gender = analytics.get('human_gender') or analytics.get('face_gender', 'unknown')
    age_group = analytics.get('human_ageGroup') or analytics.get('face_ageGroup', 'unknown')
    hair_style = analytics.get('human_hairStyle', 'unknown')
    face_expression = analytics.get('face_faceExpression', 'unknown')
    age = analytics.get('face_age', '0')
    
    update_openhab_item('Hikvision_Gender', gender)
    update_openhab_item('Hikvision_AgeGroup', age_group)
    update_openhab_item('Hikvision_HairStyle', hair_style)
    update_openhab_item('Hikvision_FaceExpression', face_expression)
    update_openhab_item('Hikvision_Age', age)
    
    # Motion
    direction = analytics.get('human_direction', 'unknown')
    update_openhab_item('Hikvision_MotionDirection', direction)
    
    # Detection quality scores
    face_score = analytics.get('face_score', '0')
    human_score = analytics.get('human_score', '0')
    update_openhab_item('Hikvision_FaceScore', face_score)
    update_openhab_item('Hikvision_HumanScore', human_score)
    
    logger.info(f"✅ Updated OpenHAB items - {gender} {age_group} (age {age}), {face_expression}, {jacket_color} jacket, {trousers_color} trousers, direction: {direction}")


@app.route('/webhook', methods=['POST', 'PUT', 'GET'])
def webhook():
    """Handle incoming webhook from Hikvision camera"""
    try:
        logger.info(f"Webhook received from {request.remote_addr}")
        
        # Get raw content as bytes (for image extraction)
        content_bytes = request.get_data()
        
        # Also get as text for JSON parsing
        content_text = content_bytes.decode('utf-8', errors='ignore')
        
        # Save raw webhook to file for analysis (when debugging)
        if LOG_WEBHOOKS and content_text:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            webhook_file = f'/etc/openhab/hikvision-analytics/webhook_{timestamp}.txt'
            with open(webhook_file, 'w') as f:
                f.write(content_text)
            logger.debug(f"Saved webhook to: {webhook_file}")
            logger.info(f"Content length: {len(content_bytes)} bytes")
            logger.debug(f"Raw content preview: {content_text[:500]}...")
            # Cleanup old webhook files
            cleanup_old_webhooks()
        
        # Extract analytics and background image from webhook
        analytics, background_image = extract_analytics_from_webhook_bytes(content_text, content_bytes)
        
        if analytics:
            logger.info("Analytics extracted successfully")
            logger.debug(f"Extracted data: {analytics}")
            
            # Update OpenHAB items
            process_analytics(analytics)
            
            # Save background image if extracted
            if background_image:
                detection_timestamp = analytics.get('human_snapTime') or analytics.get('face_snapTime', '')
                if detection_timestamp:
                    # Format timestamp for display (HH:MM:SS)
                    try:
                        dt = datetime.fromisoformat(detection_timestamp.replace('+01:00', '').replace('+00:00', ''))
                        timestamp_display = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        timestamp_display = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    save_detection_image(background_image, timestamp_display)
                else:
                    # Use current time if no timestamp in analytics
                    timestamp_display = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    save_detection_image(background_image, timestamp_display)
            else:
                logger.warning("No background image found in webhook")
        else:
            logger.warning("No analytics found in webhook")
        
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "analytics_found": analytics is not None
        }, 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500


@app.route('/test', methods=['GET'])
def test():
    """Test endpoint to verify service is running"""
    return {
        "status": "running",
        "service": "Hikvision Webhook Analytics Processor",
        "listening_on": f"0.0.0.0:{WEBHOOK_PORT}",
        "openhab_url": OPENHAB_URL,
        "timestamp": datetime.now().isoformat()
    }, 200


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        # Test OpenHAB connection
        response = requests.get(f"{OPENHAB_URL}/rest/items", timeout=2)
        openhab_ok = response.status_code == 200
    except:
        openhab_ok = False
    
    return {
        "status": "healthy" if openhab_ok else "degraded",
        "openhab_connected": openhab_ok,
        "timestamp": datetime.now().isoformat()
    }, 200 if openhab_ok else 503


if __name__ == '__main__':
    logger.info("=" * 70)
    logger.info("Hikvision Webhook Analytics Processor Starting")
    logger.info("=" * 70)
    logger.info(f"Listening on: http://0.0.0.0:{WEBHOOK_PORT}")
    logger.info(f"OpenHAB URL: {OPENHAB_URL}")
    logger.info(f"Webhook endpoint: POST http://0.0.0.0:{WEBHOOK_PORT}/webhook")
    logger.info(f"Test endpoint: GET http://0.0.0.0:{WEBHOOK_PORT}/test")
    logger.info(f"Health endpoint: GET http://0.0.0.0:{WEBHOOK_PORT}/health")
    logger.info(f"Webhook logging: {'Enabled' if LOG_WEBHOOKS else 'Disabled'}")
    logger.info(f"Max webhook files: {MAX_WEBHOOK_FILES} (auto-cleanup enabled)")
    logger.info("=" * 70)
    
    app.run(host='0.0.0.0', port=WEBHOOK_PORT, debug=False)
