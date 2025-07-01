#!/usr/bin/env python3
"""
Wistom Network Information Web Application
A dedicated Flask app for monitoring Wistom device network configuration
"""

from app import app

if __name__ == '__main__':
    print("🌐 Starting Wistom Network Information Server...")
    print("📡 Server will be available at: http://localhost:5001")
    print("🔗 Network API endpoint: http://localhost:5001/network_info")
    print("🛠️ Raw API endpoint: http://localhost:5001/api/network_info/raw")
    print("ℹ️  Press Ctrl+C to stop the server")

    app.run(
        debug=True,
        host='0.0.0.0',
        port=5001,
        threaded=True
    )
