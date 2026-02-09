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
import tempfile
import xml.etree.ElementTree as ET

# Load configuration from JSON file
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
try:
    with open(CONFIG_FILE, 'r') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print(f"❌ CRITICAL: Configuration file not found: {CONFIG_FILE}")
    print(f"⚠️  Service will use hardcoded defaults - this may cause incorrect behavior!")
    CONFIG = {}
except json.JSONDecodeError as e:
    print(f"❌ CRITICAL: Invalid JSON in configuration file: {e}")
    print(f"⚠️  Service will use hardcoded defaults - this may cause incorrect behavior!")
    CONFIG = {}

# Configuration (with fallbacks if config.json missing)
OPENHAB_URL = CONFIG.get('openhab', {}).get('url', "http://localhost:8080")
OPENHAB_TIMEOUT = CONFIG.get('openhab', {}).get('timeout_seconds', 5)
OPENHAB_HEALTH_TIMEOUT = CONFIG.get('openhab', {}).get('health_check_timeout', 2)
WEBHOOK_PORT = CONFIG.get('webhook', {}).get('port', 5001)
LOG_WEBHOOKS = CONFIG.get('webhook', {}).get('log_webhooks', True)
MAX_WEBHOOK_FILES = CONFIG.get('webhook', {}).get('max_saved_files', 50)
WEBHOOK_DIR = CONFIG.get('paths', {}).get('webhook_dir', "/etc/openhab/hikvision-analytics")
HTML_OUTPUT_PATH = CONFIG.get('paths', {}).get('html_output', "/etc/openhab/html")
IMAGE_FILENAME = CONFIG.get('files', {}).get('body_detection_image', "hikvision_latest.jpg")
TIMESTAMP_FILENAME = CONFIG.get('files', {}).get('body_detection_timestamp', "hikvision_latest_time.txt")
LINE_CROSSING_IMAGE = CONFIG.get('files', {}).get('line_crossing_image', "linecrossing_latest.jpg")
LINE_CROSSING_TIMESTAMP = CONFIG.get('files', {}).get('line_crossing_timestamp', "linecrossing_latest_time.txt")
# Extract prefix for timestamped line crossing files (remove '_latest.jpg' from filename)
LINE_CROSSING_PREFIX = LINE_CROSSING_IMAGE.replace('_latest.jpg', '').replace('.jpg', '')

# Detection configuration (target-specific thresholds for optimal detection)
# Detection configuration
POSITION_MARGIN = CONFIG.get('detection', {}).get('position_margin', 0.02)
INVERT_DIRECTION = CONFIG.get('detection', {}).get('invert_direction', False)
REGION_DIRECTION_MAP = CONFIG.get('detection', {}).get('region_direction_mapping', {})
CAMERA_RESOLUTION = CONFIG.get('detection', {}).get('camera_resolution', {'width': 1280, 'height': 720})

# Camera configuration from JSON
CAMERA_BODY = CONFIG.get('cameras', {}).get('body_detection', {})
CAMERA_LINE = CONFIG.get('cameras', {}).get('line_crossing', {})

# OpenHAB Item Names from config (with fallbacks)
body_items = CONFIG.get('items', {}).get('body_detection', {})
line_items = CONFIG.get('items', {}).get('line_crossing', {})

# Body detection item names
ITEM_CHANNEL_NAME = body_items.get('channel_name', 'Hikvision_ChannelName')
ITEM_EVENT_TYPE = body_items.get('event_type', 'Hikvision_EventType')
ITEM_TIMESTAMP = body_items.get('timestamp', 'Hikvision_Timestamp')
ITEM_JACKET_COLOR = body_items.get('jacket_color', 'Hikvision_JacketColor')
ITEM_TROUSERS_COLOR = body_items.get('trousers_color', 'Hikvision_TrousersColor')
ITEM_JACKET_TYPE = body_items.get('jacket_type', 'Hikvision_JacketType')
ITEM_TROUSERS_TYPE = body_items.get('trousers_type', 'Hikvision_TrousersType')
ITEM_HAS_HAT = body_items.get('has_hat', 'Hikvision_HasHat')
ITEM_HAS_GLASSES = body_items.get('has_glasses', 'Hikvision_HasGlasses')
ITEM_HAS_BAG = body_items.get('has_bag', 'Hikvision_HasBag')
ITEM_HAS_THINGS = body_items.get('has_things', 'Hikvision_HasThings')
ITEM_HAS_MASK = body_items.get('has_mask', 'Hikvision_HasMask')
ITEM_RIDE = body_items.get('ride', 'Hikvision_Ride')
ITEM_GENDER = body_items.get('gender', 'Hikvision_Gender')
ITEM_AGE = body_items.get('age', 'Hikvision_Age')
ITEM_AGE_GROUP = body_items.get('age_group', 'Hikvision_AgeGroup')
ITEM_HAIR_STYLE = body_items.get('hair_style', 'Hikvision_HairStyle')
ITEM_FACE_EXPRESSION = body_items.get('face_expression', 'Hikvision_FaceExpression')
ITEM_MOTION_DIRECTION = body_items.get('motion_direction', 'Hikvision_MotionDirection')
ITEM_FACE_SCORE = body_items.get('face_score', 'Hikvision_FaceScore')
ITEM_HUMAN_SCORE = body_items.get('human_score', 'Hikvision_HumanScore')

# Line crossing item names
ITEM_LC_EVENT_TYPE = line_items.get('event_type', 'LineCrossing_EventType')
ITEM_LC_EVENT_STATE = line_items.get('event_state', 'LineCrossing_EventState')
ITEM_LC_EVENT_DESCRIPTION = line_items.get('event_description', 'LineCrossing_EventDescription')
ITEM_LC_DETECTION_TIME = line_items.get('detection_time', 'LineCrossing_DetectionTime')
ITEM_LC_CAMERA_IP = line_items.get('camera_ip', 'LineCrossing_CameraIP')
ITEM_LC_CAMERA_MAC = line_items.get('camera_mac', 'LineCrossing_CameraMAC')
ITEM_LC_CHANNEL_ID = line_items.get('channel_id', 'LineCrossing_ChannelID')
ITEM_LC_CHANNEL_NAME = line_items.get('channel_name', 'LineCrossing_ChannelName')
ITEM_LC_DETECTION_TARGET = line_items.get('detection_target', 'LineCrossing_DetectionTarget')
ITEM_LC_OBJECT_TYPE = line_items.get('object_type', 'LineCrossing_ObjectType')
ITEM_LC_DIRECTION = line_items.get('direction', 'LineCrossing_Direction')
ITEM_LC_TARGET_X = line_items.get('target_x', 'LineCrossing_TargetX')
ITEM_LC_TARGET_Y = line_items.get('target_y', 'LineCrossing_TargetY')
ITEM_LC_TARGET_WIDTH = line_items.get('target_width', 'LineCrossing_TargetWidth')
ITEM_LC_TARGET_HEIGHT = line_items.get('target_height', 'LineCrossing_TargetHeight')
ITEM_LC_LINE_COORDINATES = line_items.get('line_coordinates', 'LineCrossing_LineCoordinates')
ITEM_LC_REGION_ID = line_items.get('region_id', 'LineCrossing_RegionID')
ITEM_LC_SENSITIVITY = line_items.get('sensitivity', 'LineCrossing_Sensitivity')
ITEM_LC_IMAGE_FILENAME = line_items.get('image_filename', 'LineCrossing_ImageFilename')

# Setup logging (must be before validation)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate configuration values (after logger setup)
if not (0 < POSITION_MARGIN <= 1.0):
    logger.warning(f"Invalid position_margin {POSITION_MARGIN}, using default 0.02")
    POSITION_MARGIN = 0.02

# Validate CAMERA_RESOLUTION is a dict (must be after logger setup)
if not isinstance(CAMERA_RESOLUTION, dict):
    logger.warning(f"Invalid camera_resolution type (expected dict, got {type(CAMERA_RESOLUTION).__name__}), using defaults")
    CAMERA_RESOLUTION = {'width': 1280, 'height': 720}
CAMERA_WIDTH = CAMERA_RESOLUTION.get('width', 1280)
CAMERA_HEIGHT = CAMERA_RESOLUTION.get('height', 720)

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
            # Find the end of this JSON object using json.JSONDecoder
            # This is more robust than manual brace counting (handles escaped braces in strings)
            try:
                from json import JSONDecoder
                decoder = JSONDecoder()
                result, json_end_idx = decoder.raw_decode(content_text, json_start)
                json_str = content_text[json_start:json_start + json_end_idx]
            except (json.JSONDecodeError, ValueError) as json_err:
                logger.warning(f"Failed to parse JSON with decoder: {json_err}")
                # Fallback to manual brace counting (less robust but backward compatible)
                brace_count = 0
                json_end = -1
                in_string = False
                escape_next = False
                for i in range(json_start, len(content_text)):
                    char = content_text[i]
                    if escape_next:
                        escape_next = False
                        continue
                    if char == '\\':
                        escape_next = True
                        continue
                    if char == '"' and not in_string:
                        in_string = True
                    elif char == '"' and in_string:
                        in_string = False
                    elif not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break
                
                if json_end == -1:
                    logger.warning("Could not find end of JSON object")
                    return None, None
                
                json_str = content_text[json_start:json_end]
                try:
                    result = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse extracted JSON: {e}")
                    return None, None
                
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
                
                # Extract image from webhook bytes (tries high-res, falls back to cropped)
                background_image = extract_image_with_fallback(content_bytes)
                
                if len(analytics) > 2:  # More than just channel/event
                    return analytics, background_image
        
        logger.warning("Could not find valid JSON in webhook content")
        return None, None
    except Exception as e:
        logger.error(f"Error extracting analytics: {e}", exc_info=True)
        return None, None


def extract_image_from_webhook_bytes(content_bytes, image_name):
    """
    Extract specified image from webhook multipart data
    Args:
        content_bytes: Raw webhook content as bytes
        image_name: Name of the image field (e.g., 'humanBackgroundImage' or 'humanImage')
    Returns JPEG bytes if found, None otherwise
    """
    try:
        # Find image section in bytes
        marker_pattern = f'Content-Disposition: form-data; name="{image_name}"'.encode()
        marker_idx = content_bytes.find(marker_pattern)
        
        if marker_idx == -1:
            logger.debug(f"{image_name} section not found in webhook")
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
        if not jpeg_data.startswith(b'\xff\xd8'):  # JPEG SOI (Start of Image) marker
            logger.warning(f"Extracted {image_name} doesn't start with JPEG SOI marker")
            return None
        if not jpeg_data.endswith(b'\xff\xd9'):  # JPEG EOI (End of Image) marker
            logger.warning(f"Extracted {image_name} doesn't end with JPEG EOI marker (incomplete image)")
            return None
        
        logger.info(f"✅ Extracted {image_name} from webhook: {len(jpeg_data)} bytes")
        return jpeg_data
        
    except Exception as e:
        logger.error(f"Error extracting {image_name}: {e}")
        return None


def extract_image_with_fallback(content_bytes):
    """
    Extract image from webhook with fallback logic
    Priority: high-res full scene images first, then cropped images
    Returns JPEG bytes if found, None otherwise
    """
    # Try high-res full scene images (both naming conventions)
    jpeg_data = extract_image_from_webhook_bytes(content_bytes, 'humanBackgroundImage')
    if jpeg_data:
        logger.info("🎯 Using high-res full scene image (humanBackgroundImage)")
        return jpeg_data
    
    jpeg_data = extract_image_from_webhook_bytes(content_bytes, 'faceBackgroundImage')
    if jpeg_data:
        logger.info("🎯 Using high-res full scene image (faceBackgroundImage)")
        return jpeg_data
    
    # Fallback to cropped images
    logger.warning("⚠️ High-res images not found, trying cropped images as fallback")
    jpeg_data = extract_image_from_webhook_bytes(content_bytes, 'humanImage')
    if jpeg_data:
        logger.info("🎯 Using cropped person image (humanImage) as fallback")
        return jpeg_data
    
    jpeg_data = extract_image_from_webhook_bytes(content_bytes, 'faceImage')
    if jpeg_data:
        logger.info("🎯 Using cropped face image (faceImage) as fallback")
        return jpeg_data
    
    # No images found
    logger.warning("❌ No images found in webhook")
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
        # Save image atomically (temp file + rename)
        image_path = os.path.join(HTML_OUTPUT_PATH, IMAGE_FILENAME)
        with tempfile.NamedTemporaryFile(mode='wb', dir=HTML_OUTPUT_PATH, delete=False) as tmp:
            tmp.write(jpeg_data)
            temp_path = tmp.name
        os.rename(temp_path, image_path)
        logger.info(f"✅ Saved detection image: {image_path} ({len(jpeg_data)} bytes)")
        
        # Save timestamp atomically (just time part for HTML display)
        time_only = timestamp_str.split()[1] if ' ' in timestamp_str else timestamp_str
        timestamp_path = os.path.join(HTML_OUTPUT_PATH, TIMESTAMP_FILENAME)
        with tempfile.NamedTemporaryFile(mode='w', dir=HTML_OUTPUT_PATH, delete=False) as tmp:
            tmp.write(time_only)
            temp_path = tmp.name
        os.rename(temp_path, timestamp_path)
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
        response = requests.put(url, data=str(value), headers=headers, timeout=OPENHAB_TIMEOUT)
        
        if response.status_code in [200, 201, 202]:
            logger.debug(f"✓ Updated {item_name} = {value}")
            return True
        else:
            logger.warning(f"Failed to update {item_name}: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error updating {item_name}: {e}")
        return False


def extract_linedetection_from_xml(content_text, content_bytes):
    """
    Extract line crossing detection data from XML webhook content (Camera 2)
    Args:
        content_text: Webhook content as text string (for XML parsing)
        content_bytes: Webhook content as bytes (for image extraction)
    Returns tuple: (linedetection_dict, jpeg_image_bytes)
    """
    try:
        # Find XML section (starts after boundary)
        xml_start = content_text.find('<?xml version')
        if xml_start == -1:
            logger.warning("No XML content found in webhook")
            return None, None
        
        # Find end of XML (before next boundary or image data)
        # Look for the closing </EventNotificationAlert> tag
        xml_end = content_text.find('</EventNotificationAlert>', xml_start)
        if xml_end == -1:
            logger.warning("No closing XML tag </EventNotificationAlert> found")
            return None, None
        
        # Include the closing tag in the extracted content
        xml_end += len('</EventNotificationAlert>')
        xml_content = content_text[xml_start:xml_end]
        
        # Remove namespace to simplify parsing (xmlns causes issues with findtext)
        xml_content = xml_content.replace(' xmlns="http://www.hikvision.com/ver20/XMLSchema"', '')
        
        # Parse XML
        root = ET.fromstring(xml_content)
        
        # Extract data
        linedata = {}
        
        # Camera information
        linedata['camera_ip'] = root.findtext('.//ipAddress', '')
        linedata['camera_mac'] = root.findtext('.//macAddress', '')
        linedata['channel_id'] = root.findtext('.//channelID', '0')
        linedata['channel_name'] = root.findtext('.//channelName', '')
        
        # Event information
        linedata['event_type'] = root.findtext('.//eventType', '')
        linedata['event_state'] = root.findtext('.//eventState', '')
        linedata['datetime'] = root.findtext('.//dateTime', '')
        linedata['event_description'] = root.findtext('.//eventDescription', '')
        
        # Detection settings
        linedata['region_id'] = root.findtext('.//regionID', '0')
        linedata['sensitivity'] = root.findtext('.//sensitivityLevel', '0')
        linedata['detection_target'] = root.findtext('.//detectionTarget', '')
        
        # Direction - try multiple possible field names
        direction = root.findtext('.//direction', '') or \
                   root.findtext('.//crossingDirection', '') or \
                   root.findtext('.//Direction', '') or \
                   root.findtext('.//CrossingDirection', '')
        linedata['direction'] = direction
        
        # Interpret object type from detection target
        target = linedata['detection_target'].lower()
        if 'human' in target:
            linedata['object_type'] = 'Human'
        elif 'vehicle' in target or 'car' in target:
            linedata['object_type'] = 'Vehicle'
        elif target == 'others' or target == 'other':
            linedata['object_type'] = 'Unknown Object'
        else:
            linedata['object_type'] = target.title() if target else 'Unknown'
        
        # Line coordinates - extract for calculating position relative to line
        line_x1, line_x2, line_y1, line_y2 = None, None, None, None
        coords_elem = root.find('.//RegionCoordinatesList')
        if coords_elem is not None:
            coords_list_x = coords_elem.findall('.//positionX')
            coords_list_y = coords_elem.findall('.//positionY')
            if len(coords_list_x) >= 2 and len(coords_list_y) >= 2:
                try:
                    line_x1 = float(coords_list_x[0].text) / float(CAMERA_WIDTH)  # Normalize to 0-1
                    line_x2 = float(coords_list_x[1].text) / float(CAMERA_WIDTH)
                    line_y1 = float(coords_list_y[0].text) / float(CAMERA_HEIGHT)  # Normalize to 0-1
                    line_y2 = float(coords_list_y[1].text) / float(CAMERA_HEIGHT)
                except (ValueError, TypeError, AttributeError) as e:
                    logger.warning(f"Failed to parse line coordinates: {e}")
                    pass
            coords_text = ', '.join([f"({c.find('../positionX').text},{c.find('../positionY').text})" 
                                    for c in coords_elem.findall('.//RegionCoordinates') 
                                    if c.find('../positionX') is not None])
            linedata['line_coordinates'] = coords_text if coords_text else ''
        else:
            linedata['line_coordinates'] = ''
        
        # Detect line orientation (vertical vs horizontal) and calculate line position
        linedata['line_orientation'] = 'unknown'
        linedata['line_position'] = None  # Initialize
        if line_x1 is not None and line_y1 is not None and line_x2 is not None and line_y2 is not None:
            x_diff = abs(line_x1 - line_x2)
            y_diff = abs(line_y1 - line_y2)
            if y_diff > x_diff * 2:  # Y difference is much larger = vertical line
                linedata['line_orientation'] = 'vertical'
                linedata['tracking_axis'] = 'X'
                linedata['line_position'] = (line_x1 + line_x2) / 2  # X position of vertical line
            elif x_diff > y_diff * 2:  # X difference is much larger = horizontal line
                linedata['line_orientation'] = 'horizontal'
                linedata['tracking_axis'] = 'Y'
                linedata['line_position'] = (line_y1 + line_y2) / 2  # Y position of horizontal line
            else:
                # Diagonal line: track axis with larger movement
                linedata['line_orientation'] = 'diagonal'
                linedata['tracking_axis'] = 'Y' if y_diff > x_diff else 'X'
                linedata['line_position'] = (line_y1 + line_y2) / 2 if y_diff > x_diff else (line_x1 + line_x2) / 2
        
        # Target rectangle (normalized 0-1 coordinates)
        target_rect = root.find('.//TargetRect')
        if target_rect is not None:
            linedata['target_x'] = target_rect.findtext('X', '0')
            linedata['target_y'] = target_rect.findtext('Y', '0')
            linedata['target_width'] = target_rect.findtext('width', '0')
            linedata['target_height'] = target_rect.findtext('height', '0')
        else:
            linedata['target_x'] = '0'
            linedata['target_y'] = '0'
            linedata['target_width'] = '0'
            linedata['target_height'] = '0'
        
        # Calculate side/direction if camera doesn't provide it
        if not linedata['direction']:
            try:
                target_x = float(linedata['target_x'])
                target_y = float(linedata['target_y'])
                line_position = linedata.get('line_position')
                
                if linedata['line_orientation'] == 'vertical' and line_position is not None:
                    # Vertical line: compare X positions
                    if target_x < line_position - POSITION_MARGIN:
                        linedata['calculated_side'] = 'Detected left side'
                    elif target_x > line_position + POSITION_MARGIN:
                        linedata['calculated_side'] = 'Detected right side'
                    else:
                        linedata['calculated_side'] = 'At detection line'
                elif linedata['line_orientation'] == 'horizontal' and line_position is not None:
                    # Horizontal line: compare Y positions
                    if target_y < line_position - POSITION_MARGIN:
                        linedata['calculated_side'] = 'Detected above line'
                    elif target_y > line_position + POSITION_MARGIN:
                        linedata['calculated_side'] = 'Detected below line'
                    else:
                        linedata['calculated_side'] = 'At detection line'
                else:
                    linedata['calculated_side'] = 'Position unknown'
            except (ValueError, TypeError) as e:
                logger.debug(f"Error calculating line side: {e}")
                linedata['calculated_side'] = ''
        else:
            linedata['calculated_side'] = ''
        
        # Extract JPEG image from multipart data
        jpeg_data = None
        try:
            # Find JPEG start marker (0xFFD8) - standard JPEG SOI marker
            jpeg_start_idx = content_bytes.find(b'\xff\xd8')
            if jpeg_start_idx != -1:
                # Find JPEG end marker (0xFFD9)
                jpeg_end_idx = content_bytes.rfind(b'\xff\xd9')
                if jpeg_end_idx != -1:
                    jpeg_data = content_bytes[jpeg_start_idx:jpeg_end_idx + 2]
                    logger.info(f"✅ Extracted line crossing image: {len(jpeg_data)} bytes")
        except Exception as img_error:
            logger.error(f"Error extracting line crossing image: {img_error}")
        
        logger.info(f"✅ Extracted line crossing data from camera {linedata.get('camera_ip')}")
        return linedata, jpeg_data
        
    except Exception as e:
        logger.error(f"Error parsing line crossing XML: {e}", exc_info=True)
        return None, None


def process_linedetection(linedata):
    """
    Process line crossing detection data and update OpenHAB items (Camera 2)
    Args:
        linedata: Dictionary containing line crossing detection data
    """
    if not linedata:
        logger.warning("No line crossing data to process")
        return
    
    logger.info("Processing line crossing detection data...")
    
    # Event information
    update_openhab_item(ITEM_LC_EVENT_TYPE, linedata.get('event_type', ''))
    update_openhab_item(ITEM_LC_EVENT_STATE, linedata.get('event_state', ''))
    update_openhab_item(ITEM_LC_EVENT_DESCRIPTION, linedata.get('event_description', ''))
    
    # Update timestamp (convert to DateTime format)
    datetime_str = linedata.get('datetime', '')
    if datetime_str:
        try:
            # Parse ISO format: 2026-02-09T07:39:01+01:00
            dt_obj = datetime.fromisoformat(datetime_str.replace('+01:00', '').replace('+00:00', '').replace('+02:00', ''))
            # Format for OpenHAB DateTime item: ISO 8601
            update_openhab_item(ITEM_LC_DETECTION_TIME, dt_obj.isoformat())
        except Exception as e:
            logger.warning(f"Could not parse datetime: {datetime_str}, error: {e}")
    
    # Camera information
    update_openhab_item(ITEM_LC_CAMERA_IP, linedata.get('camera_ip', ''))
    update_openhab_item(ITEM_LC_CAMERA_MAC, linedata.get('camera_mac', ''))
    update_openhab_item(ITEM_LC_CHANNEL_ID, linedata.get('channel_id', '0'))
    update_openhab_item(ITEM_LC_CHANNEL_NAME, linedata.get('channel_name', ''))
    
    # Detection target and position
    detection_target = linedata.get('detection_target', '')
    object_type = linedata.get('object_type', 'Unknown')
    update_openhab_item(ITEM_LC_DETECTION_TARGET, detection_target)
    update_openhab_item(ITEM_LC_OBJECT_TYPE, object_type)
    
    # Calculate direction - prioritize regionID mapping over position-based detection
    # METHOD 1 (Preferred): Use camera's configured line crossing rules (regionID → direction)
    # METHOD 2 (Fallback): Calculate from object position after crossing
    region_id = linedata.get('region_id', '0')
    target_x = linedata.get('target_x', '')
    target_y = linedata.get('target_y', '')
    line_orientation = linedata.get('line_orientation', 'unknown')
    tracking_axis = linedata.get('tracking_axis', 'X')
    line_position = linedata.get('line_position')  # Normalized line position (can be None)
    direction_text = 'Direction Not Available'
    
    logger.info(f"🔍 Line crossing detected - RegionID:{region_id}, Line:{line_orientation} at {line_position}, Axis:{tracking_axis}, X={target_x}, Y={target_y}")
    
    try:
        # METHOD 1: Check if regionID maps to a configured direction (most reliable)
        if region_id in REGION_DIRECTION_MAP:
            configured_direction = REGION_DIRECTION_MAP[region_id].lower()
            is_enter = (configured_direction == 'enter')
            
            # Apply direction inversion if configured
            if INVERT_DIRECTION:
                is_enter = not is_enter
                logger.info(f"🔄 Direction inverted by config")
            
            if is_enter:
                if 'vehicle' in detection_target.lower():
                    direction_text = 'Vehicle Enter'
                elif 'human' in detection_target.lower():
                    direction_text = 'Human Enter'
                else:
                    direction_text = 'Object Enter'
            else:
                if 'vehicle' in detection_target.lower():
                    direction_text = 'Vehicle Exit'
                elif 'human' in detection_target.lower():
                    direction_text = 'Human Exit'
                else:
                    direction_text = 'Object Exit'
            
            logger.info(f"✅ DIRECTION from regionID {region_id}: {direction_text} (configured as '{configured_direction}')")
        
        # METHOD 2: Fall back to position-based detection if no region mapping
        else:
            if region_id != '0':
                logger.warning(f"⚠️  RegionID {region_id} not in region_direction_mapping config - falling back to position-based detection")
            
            current_x = float(target_x) if target_x else None
            current_y = float(target_y) if target_y else None
            
            # Determine which coordinate to track based on line orientation
            if tracking_axis == 'X' and current_x is not None:
                current_pos = current_x
                axis_name = 'X'
            elif tracking_axis == 'Y' and current_y is not None:
                current_pos = current_y
                axis_name = 'Y'
            else:
                current_pos = None
                axis_name = None
            
            if current_pos is not None and line_position is not None:
                # Determine which side of the line the object is on AFTER crossing
                # For horizontal line (tracking Y): A=top (small Y), B=bottom (large Y)
                # For vertical line (tracking X): A=right (large X), B=left (small X)
                
                if tracking_axis == 'Y':
                    # Horizontal line: compare Y position to line position
                    current_side = 'A' if current_pos < line_position else 'B'
                    side_description = 'above' if current_side == 'A' else 'below'
                else:
                    # Vertical line: compare X position to line position  
                    current_side = 'A' if current_pos > line_position else 'B'
                    side_description = 'right' if current_side == 'A' else 'left'
                
                logger.info(f"📍 Object is on side {current_side} ({side_description} line) | {axis_name}={current_pos:.3f}, Line={line_position:.3f}")
                
                # Since camera only alerts when crossing happens, determine direction from final position
                # If on side B after crossing → came from A → ENTER
                # If on side A after crossing → came from B → EXIT
                is_enter = (current_side == 'B')
                
                # Apply direction inversion if configured
                if INVERT_DIRECTION:
                    is_enter = not is_enter
                    logger.info(f"🔄 Direction inverted by config")
                
                if is_enter:
                    if 'vehicle' in detection_target.lower():
                        direction_text = 'Vehicle Enter'
                    elif 'human' in detection_target.lower():
                        direction_text = 'Human Enter'
                    else:
                        direction_text = 'Object Enter'
                else:
                    if 'vehicle' in detection_target.lower():
                        direction_text = 'Vehicle Exit'
                    elif 'human' in detection_target.lower():
                        direction_text = 'Human Exit'
                    else:
                        direction_text = 'Object Exit'
                
                logger.info(f"✅ DIRECTION (position-based): {direction_text} | Object crossed to side {current_side} ({side_description})")
            else:
                # No valid position coordinate or line position
                logger.warning(f"🔍 No valid position coordinate for tracking (axis={tracking_axis}, X={current_x}, Y={current_y}, Line={line_position})")
                direction_text = 'Direction Not Available'
    except Exception as e:
        logger.error(f"Error calculating direction: {e}", exc_info=True)
        direction_text = 'Direction Error'
    
    logger.info(f"✅ Final direction text: '{direction_text}'")
    
    update_openhab_item(ITEM_LC_DIRECTION, direction_text)
    
    update_openhab_item(ITEM_LC_TARGET_X, linedata.get('target_x', '0'))
    update_openhab_item(ITEM_LC_TARGET_Y, linedata.get('target_y', '0'))
    update_openhab_item(ITEM_LC_TARGET_WIDTH, linedata.get('target_width', '0'))
    update_openhab_item(ITEM_LC_TARGET_HEIGHT, linedata.get('target_height', '0'))
    
    # Detection line and settings
    update_openhab_item(ITEM_LC_LINE_COORDINATES, linedata.get('line_coordinates', ''))
    update_openhab_item(ITEM_LC_REGION_ID, linedata.get('region_id', '0'))
    update_openhab_item(ITEM_LC_SENSITIVITY, linedata.get('sensitivity', '0'))
    
    camera_ip = linedata.get('camera_ip', 'unknown')
    object_type = linedata.get('object_type', 'unknown')
    direction = linedata.get('direction', 'no direction')
    logger.info(f"✅ Updated OpenHAB line crossing items - Camera: {camera_ip}, Object: {object_type}, Direction: {direction}")


def save_linedetection_image(jpeg_data, timestamp_str):
    """
    Save line crossing detection image to HTML folder
    Args:
        jpeg_data: JPEG image bytes
        timestamp_str: Detection timestamp string
    """
    try:
        # Generate filename based on timestamp
        if timestamp_str:
            try:
                dt = datetime.fromisoformat(timestamp_str.replace('+01:00', '').replace('+00:00', '').replace('+02:00', ''))
                filename = f"{LINE_CROSSING_PREFIX}_{dt.strftime('%Y%m%d_%H%M%S')}.jpg"
                time_string = dt.strftime('%H:%M:%S')
            except (ValueError, AttributeError) as e:
                logger.debug(f"Error parsing timestamp '{timestamp_str}': {e}")
                filename = f"{LINE_CROSSING_PREFIX}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                time_string = datetime.now().strftime('%H:%M:%S')
        else:
            filename = f"{LINE_CROSSING_PREFIX}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            time_string = datetime.now().strftime('%H:%M:%S')
        
        # Save timestamped image (atomically to prevent corruption)
        image_path = os.path.join(HTML_OUTPUT_PATH, filename)
        with tempfile.NamedTemporaryFile(mode='wb', dir=HTML_OUTPUT_PATH, delete=False) as tmp:
            tmp.write(jpeg_data)
            temp_path = tmp.name
        os.chmod(temp_path, 0o664)  # Set permissions: rw-rw-r-- for web server access
        os.rename(temp_path, image_path)
        logger.info(f"✅ Saved line crossing image: {image_path} ({len(jpeg_data)} bytes)")
        
        # Also save as latest image for HTML viewer (atomically)
        latest_path = os.path.join(HTML_OUTPUT_PATH, LINE_CROSSING_IMAGE)
        with tempfile.NamedTemporaryFile(mode='wb', dir=HTML_OUTPUT_PATH, delete=False) as tmp:
            tmp.write(jpeg_data)
            temp_path = tmp.name
        os.chmod(temp_path, 0o664)  # Set permissions: rw-rw-r-- for web server access
        os.rename(temp_path, latest_path)
        
        # Save timestamp for HTML viewer (atomically)
        timestamp_path = os.path.join(HTML_OUTPUT_PATH, LINE_CROSSING_TIMESTAMP)
        with tempfile.NamedTemporaryFile(mode='w', dir=HTML_OUTPUT_PATH, delete=False) as tmp:
            tmp.write(time_string)
            temp_path = tmp.name
        os.chmod(temp_path, 0o664)  # Set permissions: rw-rw-r-- for web server access
        os.rename(temp_path, timestamp_path)
        
        # Update OpenHAB item with filename
        update_openhab_item(ITEM_LC_IMAGE_FILENAME, filename)
        
    except Exception as e:
        logger.error(f"Error saving line crossing image: {e}")


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
    update_openhab_item(ITEM_CHANNEL_NAME, channel_name)
    update_openhab_item(ITEM_EVENT_TYPE, event_type)
    
    # Use Human data preferentially (more reliable), fallback to Face
    timestamp = analytics.get('human_snapTime') or analytics.get('face_snapTime', '')
    if timestamp:
        # Format: 2026-02-08T08:29:23+01:00
        try:
            dt = datetime.fromisoformat(timestamp.replace('+01:00', '').replace('+00:00', '').replace('+02:00', ''))
            formatted_time = dt.strftime('%d-%m-%Y kl %H:%M')
            update_openhab_item(ITEM_TIMESTAMP, formatted_time)
        except (ValueError, AttributeError) as e:
            logger.debug(f"Error parsing timestamp '{timestamp}': {e}")
            update_openhab_item(ITEM_TIMESTAMP, timestamp)
    
    # Clothing
    jacket_color = analytics.get('human_jacketColor', 'unknown')
    trousers_color = analytics.get('human_trousersColor', 'unknown')
    jacket_type = analytics.get('human_jacketType', 'unknown')
    trousers_type = analytics.get('human_trousersType', 'unknown')
    
    update_openhab_item(ITEM_JACKET_COLOR, jacket_color)
    update_openhab_item(ITEM_TROUSERS_COLOR, trousers_color)
    update_openhab_item(ITEM_JACKET_TYPE, jacket_type)
    update_openhab_item(ITEM_TROUSERS_TYPE, trousers_type)
    
    # Accessories - convert yes/no to ON/OFF
    hat = analytics.get('human_hat') or analytics.get('face_hat', 'no')
    glasses = analytics.get('human_glass') or analytics.get('face_glass', 'no')
    bag = analytics.get('human_bag', 'no')
    things = analytics.get('human_things', 'no')
    mask = analytics.get('human_mask') or analytics.get('face_mask', 'no')
    ride = analytics.get('human_ride', 'no')
    
    update_openhab_item(ITEM_HAS_HAT, 'ON' if hat == 'yes' else 'OFF')
    update_openhab_item(ITEM_HAS_GLASSES, 'ON' if glasses == 'yes' else 'OFF')
    update_openhab_item(ITEM_HAS_BAG, 'ON' if bag == 'yes' else 'OFF')
    update_openhab_item(ITEM_HAS_THINGS, 'ON' if things == 'yes' else 'OFF')
    update_openhab_item(ITEM_HAS_MASK, 'ON' if mask == 'yes' else 'OFF')
    update_openhab_item(ITEM_RIDE, 'ON' if ride == 'yes' else 'OFF')
    
    # Person attributes
    gender = analytics.get('human_gender') or analytics.get('face_gender', 'unknown')
    age_group = analytics.get('human_ageGroup') or analytics.get('face_ageGroup', 'unknown')
    hair_style = analytics.get('human_hairStyle', 'unknown')
    face_expression = analytics.get('face_faceExpression', 'unknown')
    age = analytics.get('face_age', '0')
    
    update_openhab_item(ITEM_GENDER, gender)
    update_openhab_item(ITEM_AGE_GROUP, age_group)
    update_openhab_item(ITEM_HAIR_STYLE, hair_style)
    update_openhab_item(ITEM_FACE_EXPRESSION, face_expression)
    update_openhab_item(ITEM_AGE, age)
    
    # Motion
    direction = analytics.get('human_direction', 'unknown')
    update_openhab_item(ITEM_MOTION_DIRECTION, direction)
    
    # Detection quality scores
    face_score = analytics.get('face_score', '0')
    human_score = analytics.get('human_score', '0')
    update_openhab_item(ITEM_FACE_SCORE, face_score)
    update_openhab_item(ITEM_HUMAN_SCORE, human_score)
    
    logger.info(f"✅ Updated OpenHAB items - {gender} {age_group} (age {age}), {face_expression}, {jacket_color} jacket, {trousers_color} trousers, direction: {direction}")


@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook from Hikvision camera"""
    try:
        logger.info(f"Webhook received from {request.remote_addr}")
        
        # Get raw content as bytes (for image extraction)
        content_bytes = request.get_data()
        
        # Also get as text for JSON/XML parsing
        content_text = content_bytes.decode('utf-8', errors='ignore')
        
        # Save raw webhook to file for analysis (when debugging)
        if LOG_WEBHOOKS and content_text:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            webhook_file = os.path.join(WEBHOOK_DIR, f'webhook_{timestamp}.txt')
            with open(webhook_file, 'w') as f:
                f.write(content_text)
            logger.debug(f"Saved webhook to: {webhook_file}")
            logger.info(f"Content length: {len(content_bytes)} bytes")
            logger.debug(f"Raw content preview: {content_text[:500]}...")
            # Cleanup old webhook files
            cleanup_old_webhooks()
        
        # Determine event type: line crossing detection (Camera 2) or body detection (Camera 1)
        if 'linedetection' in content_text or '<eventType>linedetection</eventType>' in content_text:
            # ==================== CAMERA 2: LINE CROSSING DETECTION ====================
            logger.info("📍 Detected LINE CROSSING event from Camera 2")
            
            linedata, jpeg_image = extract_linedetection_from_xml(content_text, content_bytes)
            
            if linedata:
                logger.info("Line crossing data extracted successfully")
                logger.debug(f"Extracted line data: {linedata}")
                
                # Update OpenHAB items
                process_linedetection(linedata)
                
                # Save detection image if extracted
                if jpeg_image:
                    timestamp_str = linedata.get('datetime', '')
                    save_linedetection_image(jpeg_image, timestamp_str)
                else:
                    logger.warning("No image found in line crossing webhook")
            else:
                logger.warning("No line crossing data found in webhook")
                
            camera_name = CAMERA_LINE.get('name', 'Camera 2')
            camera_ip = CAMERA_LINE.get('ip', '10.0.11.102')
            return {
                "status": "ok",
                "event_type": "linedetection",
                "camera": f"{camera_name} ({camera_ip})",
                "timestamp": datetime.now().isoformat(),
                "data_found": linedata is not None
            }, 200
            
        else:
            # ==================== CAMERA 1: BODY DETECTION (ORIGINAL) ====================
            logger.info("👤 Detected BODY DETECTION event from Camera 1")
            
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
                            dt = datetime.fromisoformat(detection_timestamp.replace('+01:00', '').replace('+00:00', '').replace('+02:00', ''))
                            timestamp_display = dt.strftime('%Y-%m-%d %H:%M:%S')
                        except (ValueError, AttributeError) as e:
                            logger.debug(f"Error parsing detection timestamp '{detection_timestamp}': {e}")
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
            
            camera_name = CAMERA_BODY.get('name', 'Camera 1')
            camera_ip = CAMERA_BODY.get('ip', '10.0.11.101')
            return {
                "status": "ok",
                "event_type": "body_detection",
                "camera": f"{camera_name} ({camera_ip})",
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
        response = requests.get(f"{OPENHAB_URL}/rest/items", timeout=OPENHAB_HEALTH_TIMEOUT)
        openhab_ok = response.status_code == 200
    except Exception as e:
        logger.debug(f"OpenHAB health check failed: {e}")
        openhab_ok = False
    
    return {
        "status": "healthy" if openhab_ok else "degraded",
        "openhab_connected": openhab_ok,
        "timestamp": datetime.now().isoformat()
    }, 200 if openhab_ok else 503


if __name__ == '__main__':
    # Ensure required directories exist before starting
    try:
        os.makedirs(WEBHOOK_DIR, exist_ok=True)
        os.makedirs(HTML_OUTPUT_PATH, exist_ok=True)
        logger.info(f"✅ Verified directories exist: {WEBHOOK_DIR}, {HTML_OUTPUT_PATH}")
    except Exception as dir_err:
        logger.error(f"❌ Failed to create required directories: {dir_err}")
        import sys
        sys.exit(1)
    
    logger.info("=" * 70)
    logger.info("Hikvision Webhook Analytics Processor Starting")
    logger.info("=" * 70)
    logger.info(f"Configuration loaded from: {CONFIG_FILE}")
    logger.info(f"Listening on: http://0.0.0.0:{WEBHOOK_PORT}")
    logger.info(f"OpenHAB URL: {OPENHAB_URL}")
    logger.info(f"Webhook endpoint: POST http://0.0.0.0:{WEBHOOK_PORT}/webhook")
    logger.info(f"Test endpoint: GET http://0.0.0.0:{WEBHOOK_PORT}/test")
    logger.info(f"Health endpoint: GET http://0.0.0.0:{WEBHOOK_PORT}/health")
    logger.info(f"Webhook logging: {'Enabled' if LOG_WEBHOOKS else 'Disabled'}")
    logger.info(f"Max webhook files: {MAX_WEBHOOK_FILES} (auto-cleanup enabled)")
    logger.info("-" * 70)
    logger.info(f"Camera 1 (Body Detection): {CAMERA_BODY.get('name', 'Unknown')} - {CAMERA_BODY.get('ip', 'Unknown')}")
    logger.info(f"Camera 2 (Line Crossing): {CAMERA_LINE.get('name', 'Unknown')} - {CAMERA_LINE.get('ip', 'Unknown')}")
    logger.info("-" * 70)
    logger.info(f"Detection Settings:")
    logger.info(f"  Direction detection: Region-based (using camera rule IDs)")
    logger.info(f"  Region mapping: {dict(REGION_DIRECTION_MAP)}")
    logger.info(f"  Position margin: {POSITION_MARGIN*100:.1f}% | Invert direction: {INVERT_DIRECTION}")
    logger.info("=" * 70)
    
    app.run(host='0.0.0.0', port=WEBHOOK_PORT, debug=False)
