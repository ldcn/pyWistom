from flask import Flask, render_template, jsonify
import sys
import os

# Add parent directory to path to import pyWistom
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import pyWistom
    from wistomconstants import COMMAND_ID
    from wistomconfig import HOST, PORT, USER_ID, PASSWORD
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)
app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/network_info')
def get_network_info():
    try:
        with pyWistom.WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            network_data = client.get_smgr_network_info()
            return jsonify({
                'success': True,
                'data': network_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/network_info/raw')
def get_network_info_raw():
    """Get raw network info response for debugging"""
    try:
        with pyWistom.WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            raw_data = client.custom_api_request(
                COMMAND_ID['GET'], b'SMGR', b'IP##', b'')
            return jsonify({
                'success': True,
                'data': raw_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/system_info')
def get_system_info():
    """Get basic system info for context"""
    try:
        with pyWistom.WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            system_data = client.get_smgr_info()
            return jsonify({
                'success': True,
                'data': system_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
