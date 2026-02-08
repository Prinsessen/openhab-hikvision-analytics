# Hikvision Webhook Analytics Processor

## Overview
This service receives HTTP webhook notifications from Hikvision cameras with body detection analytics and updates OpenHAB items in real-time.

## Features
- ✅ Real-time webhook processing (no file polling)
- ✅ Extracts Face and Human analytics from camera
- ✅ Updates OpenHAB items automatically
- ✅ Lightweight and efficient
- ✅ Health monitoring endpoints

## Architecture
```
Hikvision Camera → Webhook (POST) → Flask Server → Parse JSON → Update OpenHAB Items
                     :5001/webhook
```

## Installation

### 1. Install Service
```bash
sudo cp /etc/openhab/hikvision-analytics/hikvision-analytics.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hikvision-analytics
sudo systemctl start hikvision-analytics
```

### 2. Configure Camera
In camera web interface:
1. Go to: **Configuration → Event → Basic Event → Notification**
2. Add HTTP notification:
   - URL: `http://10.0.5.21:5001/webhook`
   - Method: POST
   - Username/Password: (leave empty if not using auth)
3. Link to detection events:
   - **VCA → Person Arming** (or your detection type)
   - Enable "Notify Surveillance Center"

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

**Clothing:**
- `Hikvision_JacketColor` - Detected jacket color
- `Hikvision_TrousersColor` - Detected trousers color
- `Hikvision_JacketType` - Type (longSleeve, shortSleeve, etc.)
- `Hikvision_TrousersType` - Type (longTrousers, shortTrousers, etc.)

**Accessories:**
- `Hikvision_HasHat` - ON/OFF switch
- `Hikvision_HasGlasses` - ON/OFF switch
- `Hikvision_HasBag` - ON/OFF switch
- `Hikvision_HasThings` - Carrying things (ON/OFF)
- `Hikvision_HasMask` - Face mask (ON/OFF)

**Person Attributes:**
- `Hikvision_Gender` - Detected gender
- `Hikvision_AgeGroup` - Age group (young, middle, old)
- `Hikvision_HairStyle` - Hair style

**Other:**
- `Hikvision_Timestamp` - Detection timestamp
- `Hikvision_MotionDirection` - Direction of movement

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
- `webhook_processor.py` - Main webhook processor service
- `config.json` - Configuration file
- `hikvision-analytics.service` - Systemd service definition
- `backup_old/` - Old file-based monitor (archived)

## Version History
- **v2.0** (2026-02-08) - Webhook-based real-time processing
- **v1.0** (2026-02-07) - File-based monitor (deprecated)
