#!/usr/bin/env python3
"""Debug webhook extraction"""

import json
from json import JSONDecoder

fname = 'webhook_20260209_180636.txt'

with open(fname, 'r', errors='ignore') as f:
    content_text = f.read()

# Try to find JSON
json_start = content_text.find('{"ipAddress"')
if json_start == -1:
    json_start = content_text.find('{\n\t"ipAddress"')
if json_start == -1:
    json_start = content_text.find('{\n        "ipAddress"')

print(f"JSON start position: {json_start}")

if json_start != -1:
    decoder = JSONDecoder()
    result, json_end_idx = decoder.raw_decode(content_text, json_start)
    
    print(f"✓ JSON parsed successfully")
    print(f"Event type: {result.get('eventType')}")
    
    # Check PersonArmingTrackInfo
    person_arming_info = result.get('PersonArmingTrackInfo', {})
    print(f"\nHas PersonArmingTrackInfo: {bool(person_arming_info)}")
    
    if person_arming_info:
        person_info = person_arming_info.get('PersonInfo', {})
        print(f"Has PersonInfo: {bool(person_info)}")
        
        if person_info:
            print(f"PersonInfo keys: {list(person_info.keys())}")
            
            # Check Face
            face_info = person_info.get('Face', {})
            print(f"\nHas Face: {bool(face_info)}")
            if face_info:
                print(f"Face keys: {list(face_info.keys())}")
                face_capture = face_info.get('FaceCaptureResult', {})
                print(f"Has FaceCaptureResult: {bool(face_capture)}")
                if face_capture:
                    print(f"FaceCaptureResult keys: {list(face_capture.keys())[:15]}")
                    
                    # Test extracting a field
                    age_data = face_capture.get('age', {})
                    print(f"\nTesting age extraction:")
                    print(f"  age_data: {age_data}")
                    print(f"  value: {age_data.get('value')}")
                    print(f"  ageGroup: {age_data.get('ageGroup')}")
            
            # Check Human
            human_info = person_info.get('Human', {})
            print(f"\nHas Human: {bool(human_info)}")
            if human_info:
                print(f"Human keys: {list(human_info.keys())}")
                # Note the field name!
                body_capture = human_info.get('BodyCaptureResult', {})
                human_capture = human_info.get('HumanCaptureResult', {})
                print(f"Has BodyCaptureResult: {bool(body_capture)}")
                print(f"Has HumanCaptureResult: {bool(human_capture)}")
