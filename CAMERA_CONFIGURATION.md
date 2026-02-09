# Hikvision Camera Configuration for Line Crossing Detection

## Current Status
- ✅ **Object Type Detection**: Implemented (shows "Unknown Object" until camera is configured)
- ✅ **Direction Detection**: Implemented (shows "Not Configured" until camera is enabled)
- ✅ **OpenHAB Items**: `LineCrossing_ObjectType` and `LineCrossing_Direction`
- ✅ **Sitemap**: Enhanced display with color-coded object types

## Camera: 10.0.11.102 (IPdome)
**Current Settings:**
- Detection Target: `others` (generic objects)
- Direction: Not enabled

## How to Enable Human/Vehicle Detection

### Step 1: Access Camera Web Interface
1. Open browser: `http://10.0.11.102`
2. Login with admin credentials

### Step 2: Configure Line Crossing Detection
1. Navigate to: **Configuration → Event → Smart Event → Line Crossing Detection**
2. Enable the detection rule (if not already enabled)

### Step 3: Enable Human & Vehicle Detection
1. In the Line Crossing Detection settings, find **Detection Target**
2. Change from `Others` to:
   - **Human** (to detect only people)
   - **Vehicle** (to detect only vehicles)
   - **Human & Vehicle** (to detect both)
3. Click **Save**

### Step 4: Enable Direction Detection
1. In the same Line Crossing Detection settings, find **Direction**
2. Enable direction and select:
   - **A → B** (crossing from left/top to right/bottom)
   - **B → A** (crossing from right/bottom to left/top)
   - **Both** (detect crossing in either direction)
3. The camera will now send direction information in webhooks
4. Click **Save**

### Step 5: Adjust Detection Line (Optional)
1. The detection line coordinates can be adjusted in the GUI
2. Current line: Vertical at X=504, Y=46 to Y=944
3. Draw a new line if needed for better detection coverage

## Expected Results After Configuration

### Object Type Display
- **Human** → Shows "Human" in green
- **Vehicle** → Shows "Vehicle" in orange  
- **Others** → Shows "Unknown Object" in silver (current state)

### Direction Display
When configured, direction will show as:
- **A → B (Left to Right)** or **A → B (Entering)**
- **B → A (Right to Left)** or **B → A (Leaving)**
- Current: "Not Configured" in silver

## OpenHAB Items
```openhab
LineCrossing_ObjectType      "Object Type [%s]"         (Shows: Human, Vehicle, Unknown Object)
LineCrossing_Direction       "Crossing Direction [%s]"  (Shows: A→B, B→A, Not Configured)
LineCrossing_DetectionTarget "Detection Target [%s]"    (Raw camera value: human, vehicle, others)
```

## Sitemap Display
The enhanced sitemap now shows:
1. **Latest Detection** (top frame):
   - Object Detected: Human/Vehicle/Unknown (color-coded)
   - Direction: A→B or B→A
   - Time: Detection timestamp
2. **Event Information**: Event type, state, description, raw target
3. **Camera Information**: IP, MAC, channel
4. **Target Position**: X, Y, width, height coordinates
5. **Detection Settings**: Line coordinates, region ID, sensitivity
6. **Detection Snapshot**: Image filename and snapshot display

## Webhook Data Structure
### Current XML (before configuration):
```xml
<detectionTarget>others</detectionTarget>
<!-- No direction field -->
```

### After Camera Configuration:
```xml
<detectionTarget>human</detectionTarget>
<direction>left</direction>  <!-- or 'right', 'enter', 'leave' -->
```

## Testing
After configuring the camera, trigger a line crossing event:
1. Walk/drive across the detection line
2. Check OpenHAB items:
   ```bash
   curl http://localhost:8080/rest/items/LineCrossing_ObjectType/state
   curl http://localhost:8080/rest/items/LineCrossing_Direction/state
   ```
3. Expected: "Human" and "A → B" (or similar)

## Troubleshooting
- **Still shows "Unknown Object"**: Camera detection target not configured
- **Still shows "Not Configured"**: Camera direction detection not enabled
- **No detections**: Check sensitivity level (current: 50), try increasing to 100
- **Too many detections**: Decrease sensitivity or adjust detection line position

## Notes
- The webhook processor automatically maps camera values to friendly names
- Infrastructure is ready - configuration changes take effect immediately
- No OpenHAB restart needed after camera configuration
- Direction mapping: left→A→B, right→B→A, enter→A→B, leave→B→A
