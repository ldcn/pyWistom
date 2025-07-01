import base64
import io
import numpy as np
import matplotlib.pyplot as plt
from flask import Flask, render_template, jsonify
from pyWistom import WistomClient, COMMAND_ID
from wistomconfig import HOST, PORT, USER_ID, PASSWORD
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/spectrum')
def get_spectrum():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            spectrum_data = client.custom_api_request(
                COMMAND_ID['GET'], b'WSNS', b'DATA', bytes.fromhex("0a01"))

            if 'response' in spectrum_data and 'spectrum_data_values' in spectrum_data['response']:
                values = spectrum_data['response']['spectrum_data_values']

                # Create plot
                plt.figure(figsize=(10, 6))
                plt.plot(values)
                plt.title("Sensor Spectrum")
                plt.xlabel("Frequency [GHz]")
                plt.ylabel("Reflectivity [dB]")
                plt.grid(True)

                # Save plot to base64 string
                img = io.BytesIO()
                plt.savefig(img, format='png')
                img.seek(0)
                plot_url = base64.b64encode(img.getvalue()).decode()
                plt.close()

                return jsonify({
                    'success': True,
                    'plot': plot_url,
                    'data': values[:10]  # First 10 values for preview
                })
            else:
                return jsonify({'success': False, 'error': 'No spectrum data found'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/peaks')
def get_peaks():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()

            # Get hardware parameters
            hw_params = client.custom_api_request(
                COMMAND_ID['GET'], b'WSNS', b'PARA', b'')

            # Get spectrum data
            spectrum_data = client.custom_api_request(
                COMMAND_ID['GET'], b'WSNS', b'DATA', bytes.fromhex("0a01"))

            if 'response' in spectrum_data and 'spectrum_data_values' in spectrum_data['response']:
                values = np.array(
                    spectrum_data['response']['spectrum_data_values'])

                # Hardware-based peak detection
                peaks = detect_peaks_with_hardware_params(values, hw_params)

                return jsonify({
                    'success': True,
                    'peak_count': len(peaks['positions']),
                    'peaks': peaks['positions'],
                    'peak_details': peaks['details'],
                    'threshold': float(peaks['threshold']),
                    'hardware_params': peaks['hardware_params_used']
                })
            else:
                return jsonify({'success': False, 'error': 'No spectrum data found'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/peaks/<threshold_method>')
def get_peaks_with_method(threshold_method):
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()

            # Get hardware parameters
            hw_params = client.custom_api_request(
                COMMAND_ID['GET'], b'WSNS', b'PARA', b'')

            # Get spectrum data
            spectrum_data = client.custom_api_request(
                COMMAND_ID['GET'], b'WSNS', b'DATA', bytes.fromhex("0a01"))

            if 'response' in spectrum_data and 'spectrum_data_values' in spectrum_data['response']:
                values = np.array(
                    spectrum_data['response']['spectrum_data_values'])

                # Hardware-based peak detection with specified threshold method
                peaks = detect_peaks_with_hardware_params(
                    values, hw_params, threshold_method)

                return jsonify({
                    'success': True,
                    'peak_count': len(peaks['positions']),
                    'peaks': peaks['positions'],
                    'peak_details': peaks['details'],
                    'threshold': float(peaks['threshold']),
                    'hardware_params': peaks['hardware_params_used'],
                    'threshold_method': threshold_method
                })
            else:
                return jsonify({'success': False, 'error': 'No spectrum data found'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


def detect_peaks_with_hardware_params(data, hw_params, threshold_method='auto'):
    """
    Detect peaks using hardware parameters from WSNS PARA command

    Parameters:
    - data: numpy array of spectrum values
    - hw_params: hardware parameters from WSNS PARA response
    - threshold_method: 'port_threshold', 'calculated', or 'auto'

    Returns:
    - Dictionary with peak positions, details, threshold, and hardware params used
    """
    # Extract hardware parameters
    response = hw_params.get('response', {})

    # Get relevant parameters for peak detection
    peak_height_ref = response.get('peak_height_reference_lines', 2.0)
    frequency_delta = response.get('frequency_delta', 1.0)
    filter_constant = response.get('filter_constant', 0.1)
    white_light_min = response.get('white_light_minimum', 0.0)
    interferometer_start_amp = response.get(
        'interferometer_start_amplitude', 1000.0)
    interferometer_min_step = response.get('interferometer_minimum_step', 10)

    # Get port-specific thresholds (assuming we're using port 1)
    port_threshold = response.get('port_1_threshold', None)

    # Calculate dynamic threshold based on hardware parameters
    data_mean = np.mean(data)
    data_std = np.std(data)

    # Calculate both threshold options
    calculated_threshold = data_mean + \
        peak_height_ref * data_std * (1 + filter_constant)

    # Choose threshold based on method
    if threshold_method == 'port_threshold' and port_threshold is not None:
        threshold = float(port_threshold)
        threshold_source = 'port_threshold'
    elif threshold_method == 'calculated':
        threshold = calculated_threshold
        threshold_source = 'calculated'
    else:  # 'auto' - use port_threshold if available, otherwise calculated
        if port_threshold is not None:
            threshold = float(port_threshold)
            threshold_source = 'port_threshold'
        else:
            threshold = calculated_threshold
            threshold_source = 'calculated'

    # Use interferometer minimum step as minimum peak distance
    min_peak_distance = max(int(interferometer_min_step), 5)

    # Use frequency delta to determine minimum FWHM
    min_fwhm = max(int(frequency_delta * 2), 3)

    # Find initial candidates (local maxima above threshold)
    candidates = []
    for i in range(1, len(data) - 1):
        if (data[i] > data[i-1] and
            data[i] > data[i+1] and
                data[i] > threshold):
            candidates.append(i)

    # Filter candidates based on hardware-derived FWHM and peak distance
    valid_peaks = []
    peak_details = []

    for peak_idx in candidates:
        peak_height = data[peak_idx]

        # Use white light minimum as baseline for half-maximum calculation
        baseline = max(white_light_min, np.min(
            data[max(0, peak_idx-20):min(len(data), peak_idx+20)]))
        half_max = baseline + (peak_height - baseline) / 2

        # Find left half-maximum point
        left_half_max = peak_idx
        for i in range(peak_idx, max(0, peak_idx - 100), -1):
            if data[i] <= half_max:
                left_half_max = i
                break

        # Find right half-maximum point
        right_half_max = peak_idx
        for i in range(peak_idx, min(len(data), peak_idx + 100)):
            if data[i] <= half_max:
                right_half_max = i
                break

        # Calculate FWHM
        fwhm = right_half_max - left_half_max

        # Check if peak meets hardware-based FWHM criteria
        if fwhm >= min_fwhm:
            # Check minimum distance from other valid peaks
            too_close = False
            for existing_peak in valid_peaks:
                if abs(peak_idx - existing_peak) < min_peak_distance:
                    # Keep the higher peak if they're too close
                    if data[peak_idx] > data[existing_peak]:
                        valid_peaks.remove(existing_peak)
                        # Remove corresponding detail
                        peak_details = [detail for detail in peak_details
                                        if detail['position'] != existing_peak]
                    else:
                        too_close = True
                    break

            if not too_close:
                valid_peaks.append(peak_idx)

                # Calculate signal-to-noise ratio using interferometer start amplitude
                snr = peak_height / \
                    max(interferometer_start_amp / 1000, data_std)

                peak_details.append({
                    'position': int(peak_idx),
                    'height': float(peak_height),
                    'fwhm': int(fwhm),
                    'left_half_max': int(left_half_max),
                    'right_half_max': int(right_half_max),
                    'prominence': float(peak_height - threshold),
                    'baseline': float(baseline),
                    'snr': float(snr)
                })

    # Sort peaks by position
    valid_peaks.sort()
    peak_details.sort(key=lambda x: x['position'])

    # Prepare hardware parameters info for response
    hardware_params_used = {
        'peak_height_reference_lines': peak_height_ref,
        'frequency_delta': frequency_delta,
        'filter_constant': filter_constant,
        'white_light_minimum': white_light_min,
        'interferometer_start_amplitude': interferometer_start_amp,
        'interferometer_minimum_step': interferometer_min_step,
        'port_threshold': port_threshold,
        'calculated_threshold': float(calculated_threshold),
        'used_threshold': float(threshold),
        'threshold_source': threshold_source,
        'min_peak_distance': min_peak_distance,
        'min_fwhm': min_fwhm
    }

    return {
        'positions': valid_peaks,
        'details': peak_details,
        'threshold': threshold,
        'hardware_params_used': hardware_params_used
    }


@app.route('/smgr_info')
def smgr_info():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            smgr_data = client.get_smgr_info()
            return jsonify({
                'success': True,
                'data': smgr_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/smgr_network_info')
def smgr_network_info():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
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


@app.route('/smgr_serial_settings')
def smgr_serial_settings():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            serial_data = client.get_smgr_serial_settings()
            return jsonify({
                'success': True,
                'data': serial_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/smgr_time')
def smgr_time():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            time_data = client.get_smgr_time()
            return jsonify({
                'success': True,
                'data': time_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/smgr_temp')
def smgr_temp():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            temp_data = client.get_smgr_temp()
            return jsonify({
                'success': True,
                'data': temp_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/smgr_uptime')
def smgr_uptime():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            uptime_data = client.get_smgr_uptime()
            return jsonify({
                'success': True,
                'data': uptime_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/snmp_agent_port')
def snmp_agent_port():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            snmp_data = client.get_snmp_agent_listening_port()
            return jsonify({
                'success': True,
                'data': snmp_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/snmp_trap_receivers')
def snmp_trap_receivers():
    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            login_response = client.login()
            trap_data = client.get_snmp_trap_receivers()
            return jsonify({
                'success': True,
                'data': trap_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/smgr')
def smgr_page():
    return render_template('smgr.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
