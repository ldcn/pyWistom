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
            spectrum_data = client.custom_api_request(
                COMMAND_ID['GET'], b'WSNS', b'DATA', bytes.fromhex("0a01"))

            if 'response' in spectrum_data and 'spectrum_data_values' in spectrum_data['response']:
                values = np.array(
                    spectrum_data['response']['spectrum_data_values'])

                # Simple peak detection using numpy
                # Find peaks that are above the mean + 1 standard deviation
                threshold = np.mean(values) + np.std(values)
                peaks = []
                for i in range(1, len(values) - 1):
                    if values[i] > values[i-1] and values[i] > values[i+1] and values[i] > threshold:
                        peaks.append(i)

                return jsonify({
                    'success': True,
                    'peak_count': len(peaks),
                    'peaks': peaks,
                    'threshold': float(threshold)
                })
            else:
                return jsonify({'success': False, 'error': 'No spectrum data found'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
