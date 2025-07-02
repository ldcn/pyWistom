# Wistom Network Information Web App
A dedicated Flask web application for monitoring and displaying Wistom device network configuration in real-time.

## Features

- **Real-time Network Monitoring**: Auto-refresh network information every 10 seconds
- **Visual Status Indicators**: Color-coded status for connection, DHCP, and response times
- **Modern UI**: Responsive design with smooth animations and card-based layout
- **Raw Data Access**: View raw API responses for debugging
- **Mobile Friendly**: Responsive design works on all device sizes
- **Fast Performance**: Lightweight and optimized for quick loading

## Quick Start

1. **Install Dependencies**:
   ```bash
   cd network_app
   pip install -r requirements.txt
   ```

2. **Configure Connection**:
   Make sure your `wistomconfig.py` in the parent directory has the correct settings:
   ```python
   HOST = "your_wistom_device_ip"
   PORT = 443
   USER_ID = "your_username"
   PASSWORD = "your_password"
   ```

3. **Run the Application**:
   ```bash
   python run.py
   ```

4. **Access the Web Interface**:
   Open your browser to: `http://localhost:5001`

## API Endpoints

- `GET /` - Main dashboard interface
- `GET /network_info` - Parsed network information (JSON)
- `GET /api/network_info/raw` - Raw API response (JSON)
- `GET /api/system_info` - Basic system information (JSON)

## Network Information Displayed

### High Priority
- **IP Address** - Current device IP
- **Subnet Mask** - Network mask
- **Gateway** - Default gateway

### Medium Priority  
- **MAC Address** - Hardware address
- **DNS Server** - DNS configuration
- **Hostname** - Device hostname

### Low Priority
- **TCP Port** - Communication port

## Features in Detail

### Auto Refresh
- Toggle automatic refresh on/off
- 10-second refresh interval
- Visual indicator when enabled
- Stops on connection errors

### Status Monitoring
- **Connection Status**: Real-time connection health
- **DHCP Status**: Dynamic IP configuration state
- **Response Time**: API call latency
- **Last Check**: Timestamp of last successful update

### Raw Data View
- Complete API response data
- JSON formatted for readability
- Copy to clipboard functionality
- Useful for debugging and development

### Data Validation
- IP address format validation
- MAC address format checking
- Subnet/gateway relationship warnings
- Visual indicators for data issues

## Customization

### Styling
Edit `static/css/style.css` to customize the appearance:
- Color schemes
- Layout adjustments
- Font preferences
- Animation speeds

### Refresh Intervals
Modify `CONFIG.autoRefreshInterval` in `static/js/main.js`:
```javascript
const CONFIG = {
    autoRefreshInterval: 5000, // 5 seconds instead of 10
    // ...
};
```

### Additional Fields
Add new network fields in the `networkFields` array in `templates/index.html`.

## Troubleshooting

### Connection Issues
1. Verify `wistomconfig.py` settings
2. Check network connectivity to device
3. Ensure device API is accessible
4. Check firewall settings

### Port Conflicts
If port 5001 is in use, change it in `run.py`:
```python
app.run(port=5002)  # Use different port
```

### SSL/TLS Issues
If you encounter SSL errors, the main `pyWistom.py` might need SSL configuration.

## Development

### Adding New Features
1. Add route to `app.py`
2. Update templates in `templates/`
3. Add styling to `static/css/style.css`
4. Add JavaScript to `static/js/main.js`

### Testing
```bash
# Run with debug mode
python run.py

# Test API endpoints
curl http://localhost:5001/network_info
curl http://localhost:5001/api/system_info
```

## License

This project is part of the pyWistom toolkit.