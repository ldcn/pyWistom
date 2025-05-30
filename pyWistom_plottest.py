from pyWistom import WistomClient, COMMAND_ID
from wistomconfig import HOST, PORT, USER_ID, PASSWORD
import numpy as np

with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
    login_response = client.login()
    print("Login Response:", login_response)
    spectrum_data = client.custom_api_request(
        COMMAND_ID['GET'], b'WSNS', b'DATA', bytes.fromhex("0a01"))
    import matplotlib.pyplot as plt

    # Assuming spectrum_data is a list or array of numerical values
    if isinstance(spectrum_data['response']['spectrum_data_values'],
                  (list, np.ndarray)):
        plt.plot(spectrum_data['response']['spectrum_data_values'])
        plt.title("Spectrum Data")
        plt.xlabel("Index")
        plt.ylabel("Value")
        plt.grid(True)
        plt.show()
    else:
        print("Spectrum data is not in a plottable format:", spectrum_data)
