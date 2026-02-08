# Hikvision Webhook Analytics Processor

## Overview
This service receives HTTP webhook notifications from Hikvision cameras with body detection analytics and updates OpenHAB items in real-time.

## Features
- ✅ Real-time webhook processing (no file polling)
- ✅ Extracts 26+ analytics fields from Face and Human detection
- ✅ Extracts high-resolution detection images from webhook
- ✅ Updates 18 OpenHAB items automatically via REST API
- ✅ Auto-cleanup: keeps last 50 webhook files
- ✅ Systemd service with auto-restart on boot
- ✅ Health monitoring endpoints
- ✅ No NAS dependency - images embedded in webhooks

## Architecture
```
Hikvision Camera → Webhook (POST) → Flask Server → Parse JSON → Update OpenHAB Items
                     :5001/webhook                    ↓
                                                Extract Images → /etc/openhab/html/
```

### How It Works
1. **Camera Detection**: Hikvision camera analyzes video for persons/faces
2. **Webhook POST**: Camera sends multipart HTTP POST with:
   - JSON analytics (26+ fields from Face + Human detection)
   - 3 JPEG images (faceImage, faceBackgroundImage, humanImage)
3. **Flask Processing**: 
   - Extracts analytics from JSON (gender, age, clothing, accessories, etc.)
   - Extracts faceBackgroundImage (high-res scene capture)
   - Updates 18 OpenHAB items via REST API
   - Saves detection image to `/etc/openhab/html/hikvision_latest.jpg`
4. **OpenHAB Display**: Sitemap shows real-time data + image via webview

## Installation

### 1. Install Dependencies
```bash
cd /etc/openhab/hikvision-analytics
python3 -m venv .venv
source .venv/bin/activate
pip install flask requests
```

### 2. Configure Settings
Copy example config and edit with your details:
```bash
cp config.example.json config.json
nano config.json
```

Update camera IP and server IP in `config.json`.

### 3. Install Service
```bash
sudo cp hikvision-analytics.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hikvision-analytics
sudo systemctl start hikvision-analytics
```

### 4. Configure Camera Webhook
**Important:** The camera must send webhooks to this service.

#### Access Camera Web Interface
1. Open browser: `http://YOUR_CAMERA_IP`
2. Login with admin credentials

#### Setup HTTP Notification
Navigate to: **Configuration → Event → Basic Event → HTTP Listening**

1. **Enable HTTP Listening**
2. **Add HTTP Server:**
   - **URL**: `http://YOUR_OPENHAB_SERVER_IP:5001/webhook`
   - **Protocol**: HTTP
   - **Port**: 5001
   - **URL Path**: `/webhook`
   - **Method**: POST
   - **Username/Password**: Leave empty (unless you added authentication)

#### Link to Detection Events
Navigate to: **Configuration → Event → Smart Event → Body Detection** (or Person Detection)

1. **Enable Body Detection** rule
2. **Enable Linkage Method**: Check "Notify Surveillance Center"
3. **Arming Schedule**: Set to 24/7 or desired schedule
4. **Save** settings

#### Test Webhook
Walk in front of camera and check:
```bash
# Check service received webhook
sudo journalctl -u hikvision-analytics -f

# Verify OpenHAB items updated
curl http://localhost:8080/rest/items/Hikvision_Gender
```

## Display Detection Image in OpenHAB

The service extracts and saves detection images to `/etc/openhab/html/hikvision_latest.jpg`

### Create HTML Display
Create `/etc/openhab/html/hikvision_detections.html`:
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3">
    <title>Hikvision Detection</title>
    <style>
        body {
            margin: 0;
            padding: 10px;
            background: #1c1c1c;
            font-family: Arial, sans-serif;
        }
        .container {
            text-align: center;
        }
        img {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .timestamp {
            color: #00ff00;
            font-size: 14px;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <img src="hikvision_latest.jpg" alt="Latest Detection">
        <div class="timestamp" id="time">Loading...</div>
    </div>
    <script>
        fetch('hikvision_latest_time.txt')
            .then(r => r.text())
            .then(t => document.getElementById('time').textContent = 'Detected: ' + t)
            .catch(() => document.getElementById('time').textContent = 'No detection yet');
    </script>
</body>
</html>
```

### Add to Sitemap
In your sitemap file:
```openhab
Frame label="Body Detection Camera" {
    Webview url="/static/hikvision_detections.html" height=10
    Text item=Hikvision_Timestamp icon="hikvision-time-cyan" label="Detection Time [%s]"
    Text item=Hikvision_Gender icon="hikvision-person-orange" label="Gender: [%s]"
    Text item=Hikvision_JacketColor icon="hikvision-color-pink" label="Jacket: [%s]"
    Text item=Hikvision_TrousersColor icon="hikvision-color-pink" label="Trousers: [%s]"
}
```

The image refreshes automatically every 3 seconds.

## Usage

### Check Service Status
```bash
sudo systemctl status hikvision-analytics
```

### View Logs
```bash
sudo journalctl -u hikvision-analytics -f
```

### Test Endpoints
```bash
# Test if service is running
curl http://localhost:5001/test

# Health check
curl http://localhost:5001/health
```

### Manual Test
Trigger a detection on the camera (walk by), then check OpenHAB items:
```bash
# Check via REST API
curl http://localhost:8080/rest/items/Hikvision_JacketColor
curl http://localhost:8080/rest/items/Hikvision_TrousersColor
```

## OpenHAB Items
The service updates these items (defined in `items/hikvision_detection.items`):

**Detection Info:**
- `Hikvision_Timestamp` - Detection timestamp (DateTime)
- `Hikvision_ChannelName` - Camera channel name
- `Hikvision_EventType` - Event type (e.g., mixedTargetDetection)

**Person Attributes:**
- `Hikvision_Gender` - Detected gender (male/female)
- `Hikvision_Age` - Estimated age in years (Number)
- `Hikvision_AgeGroup` - Age group (young/middle/old)
- `Hikvision_FaceExpression` - Expression (smile/neutral/frown/happy)
- `Hikvision_HairStyle` - Hair style detection

**Clothing:**
- `Hikvision_JacketColor` - Jacket color
- `Hikvision_JacketType` - Type (longSleeve/shortSleeve/etc.)
- `Hikvision_TrousersColor` - Trousers color
- `Hikvision_TrousersType` - Type (longTrousers/shortTrousers/etc.)

**Accessories:**
- `Hikvision_HasHat` - Hat detected (Switch ON/OFF)
- `Hikvision_HasGlasses` - Glasses detected (Switch ON/OFF)
- `Hikvision_HasMask` - Face mask detected (Switch ON/OFF)
- `Hikvision_HasBag` - Bag/backpack detected (Switch ON/OFF)
- `Hikvision_HasThings` - Carrying items (Switch ON/OFF)

**Motion & Quality:**
- `Hikvision_MotionDirection` - Direction (forward/backward/left/right)
- `Hikvision_FaceScore` - Face detection confidence (0-100%)
- `Hikvision_HumanScore` - Body detection confidence (0-100%)

## Configuration
Edit `config.json` to customize:
- Webhook port (default: 5001)
- OpenHAB URL (default: http://localhost:8080)
- Logging options

## Troubleshooting

### Service won't start
Check permissions:
```bash
sudo chown openhab:openhab /etc/openhab/hikvision-analytics/webhook_processor.py
sudo chmod +x /etc/openhab/hikvision-analytics/webhook_processor.py
```

### Not receiving webhooks
1. Check camera notification configuration
2. Verify firewall allows port 5001:
   ```bash
   sudo ufw allow 5001/tcp
   ```
3. Test from camera IP:
   ```bash
   curl -X POST http://10.0.5.21:5001/webhook
   ```

### Items not updating
1. Check OpenHAB connection: `curl http://localhost:5001/health`
2. Verify item names match in `items/hikvision_detection.items`
3. Check logs: `sudo journalctl -u hikvision-analytics -f --since "5 minutes ago"`

## Files
- `webhook_processor.py` - Main Flask webhook processor (408 lines)
- `config.json` - Configuration file (not in repo - see config.example.json)
- `config.example.json` - Example configuration template
- `hikvision-analytics.service` - Systemd service definition
- `.gitignore` - Protects sensitive data and test files
- `README.md` - This file

**Output Files (auto-generated):**
- `/etc/openhab/html/hikvision_latest.jpg` - Latest detection image
- `/etc/openhab/html/hikvision_latest_time.txt` - Detection timestamp
- `webhook_*.txt` - Webhook logs (kept for debugging, last 50 files)

## Version History
- **v2.0** (2026-02-08) - Webhook-based real-time processing
- **v1.0** (2026-02-07) - File-based monitor (deprecated)

## Author
**Nanna Agesen**  
📧 Nanna@Agesen.dk  
🐙 GitHub: [@Prinsessen](https://github.com/Prinsessen)
