#!/usr/bin/env python3

import requests
import json

def test_api():
    try:
        response = requests.get('http://localhost:8000/api/defaults')
        if response.status_code == 200:
            data = response.json()
            print("API Response:")
            print(json.dumps(data, indent=2))

            # Check if orbit data is present
            orbit = data.get('initial_conditions', {}).get('orbit', {})
            print("\nOrbit data:")
            print(json.dumps(orbit, indent=2))

            if orbit:
                print("\nOrbit fields found:")
                for key, value in orbit.items():
                    print(f"  {key}: {value}")
            else:
                print("\nNo orbit data found!")
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_api()
