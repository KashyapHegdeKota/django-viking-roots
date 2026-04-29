import requests
import json
import sys

# CONFIGURATION
BACKEND_URL = "http://localhost:8000" # Change if your server is on a different port
WEBHOOK_KEY = "bF7wQ9zL2xN8mK4pR1vT6yH3uJ5cD0eS7gA2nP9qW4rY8tU1iO6lZ3xC5vB0mN7kJ2"

def simulate_webhook(post_id, user_id_to_tag):
    url = f"{BACKEND_URL}/api/recognition/webhook/lambda-recognition/"
    
    headers = {
        "Content-Type": "application/json",
        "X-Lambda-Auth-Key": WEBHOOK_KEY
    }
    
    # This matches the payload structure the backend expects from Lambda
    payload = {
        "post_id": post_id,
        "matches": [
            {
                "user_id": user_id_to_tag,
                "face_id": "mock-face-id-123",
                "confidence": 98.5,
                "bounding_box": {
                    "Top": 0.1,
                    "Left": 0.1,
                    "Width": 0.2,
                    "Height": 0.2
                }
            }
        ]
    }
    
    print(f"--- Simulating Lambda Webhook ---")
    print(f"Target Post ID: {post_id}")
    print(f"User ID to Tag: {user_id_to_tag}")
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("\nSUCCESS! Check your Social Feed now. The user should be tagged on the post.")
        else:
            print("\nFAILED. Check your server logs for errors.")
            
    except Exception as e:
        print(f"Error connecting to server: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python simulate_lambda_webhook.py <post_id> <user_id_to_tag>")
        print("Example: python simulate_lambda_webhook.py 5 2")
    else:
        simulate_webhook(int(sys.argv[1]), int(sys.argv[2]))
