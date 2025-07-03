from flask import Flask, render_template, jsonify, request
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


@app.route('/api/set_network_config', methods=['POST'])
def set_network_config():
    try:
        data = request.get_json()

        with pyWistom.WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()

            # Extract parameters from request
            params = {}
            if 'ip_address' in data:
                params['ip_address'] = data['ip_address']
            if 'subnet_mask' in data:
                params['subnet_mask'] = data['subnet_mask']
            if 'gateway' in data:
                params['gateway'] = data['gateway']
            if 'hostname' in data:
                params['hostname'] = data['hostname']
            if 'mac_address' in data:
                params['mac_address'] = data['mac_address']
            if 'tcp_port' in data:
                params['tcp_port'] = int(data['tcp_port'])

            # Set the network configuration
            results = client.set_smgr_network_config(**params)

            return jsonify({
                'success': True,
                'message': 'Network configuration updated successfully',
                'results': results
            })

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Validation error: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/set_ip', methods=['POST'])
def set_ip_address():
    try:
        data = request.get_json()
        ip_address = data.get('ip_address')

        if not ip_address:
            return jsonify({'success': False, 'error': 'IP address required'}), 400

        with pyWistom.WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            result = client.set_ip_address(ip_address)

            # Flash ROM to save changes permanently
            flash_result = client.custom_api_request(
                COMMAND_ID['SET'], b'SMGR', b'FLSH', b'\x01\x00')

            return jsonify({
                'success': True,
                'message': f'IP address set to {ip_address} and saved to ROM',
                'result': result,
                'flash_result': flash_result
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/validate_network_config', methods=['POST'])
def validate_network_config():
    """Validate network configuration without applying it"""
    try:
        data = request.get_json()
        errors = []

        # Validate IP address
        if 'ip_address' in data:
            if not validate_ip_address(data['ip_address']):
                errors.append('Invalid IP address format')

        # Validate subnet mask
        if 'subnet_mask' in data:
            if not validate_ip_address(data['subnet_mask']):
                errors.append('Invalid subnet mask format')

        # Validate gateway
        if 'gateway' in data:
            if not validate_ip_address(data['gateway']):
                errors.append('Invalid gateway address format')

        # Validate hostname
        if 'hostname' in data:
            hostname = data['hostname']
            if not (1 <= len(hostname) <= 255):
                errors.append('Hostname must be 1-255 characters')
            if not hostname.replace('-', '').replace('_', '').isalnum():
                errors.append('Hostname contains invalid characters')

        # Validate TCP port
        if 'tcp_port' in data:
            try:
                port = int(data['tcp_port'])
                if not (1 <= port <= 65535):
                    errors.append('TCP port must be between 1 and 65535')
            except (ValueError, TypeError):
                errors.append('Invalid TCP port number')

        if errors:
            return jsonify({
                'success': False,
                'error': '; '.join(errors)
            }), 400

        return jsonify({
            'success': True,
            'message': 'Configuration is valid'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def validate_ip_address(ip):
    """Validate IP address format"""
    import re
    pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    return bool(re.match(pattern, ip))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
