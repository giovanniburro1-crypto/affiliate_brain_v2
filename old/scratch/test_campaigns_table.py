import sys
import os

# Add parent directory to path to import backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_endpoint():
    print("Testing /api/metrics/campaigns-table with no source...")
    response = client.get("/api/metrics/campaigns-table?period=14")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Success! Found {len(data.get('campaigns', []))} campaigns.")
    else:
        print(f"Error: {response.text}")

    print("\nTesting /api/metrics/campaigns-table with multiselect source...")
    # We need to know some real sources to test. Let's first get sources.
    src_resp = client.get("/api/metrics/sources?period=14")
    sources = src_resp.json().get('sources', [])
    print(f"Available sources: {sources}")
    
    if len(sources) >= 2:
        test_sources = ",".join(sources[:2])
        print(f"Testing with sources: {test_sources}")
        response = client.get(f"/api/metrics/campaigns-table?period=14&source={test_sources}")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Success! Found {len(data.get('campaigns', []))} campaigns.")
        else:
            print(f"Error: {response.text}")
    elif len(sources) == 1:
        print(f"Only one source found: {sources[0]}")
        response = client.get(f"/api/metrics/campaigns-table?period=14&source={sources[0]}")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Success! Found {len(data.get('campaigns', []))} campaigns.")
        else:
            print(f"Error: {response.text}")
    else:
        print("No sources found in DB.")

if __name__ == "__main__":
    test_endpoint()
