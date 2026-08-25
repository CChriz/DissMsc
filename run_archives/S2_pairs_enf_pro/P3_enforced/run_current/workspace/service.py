"""Service module that calls 3 external APIs."""
import requests


BASE_USER_URL = "https://api.users.example.com/v1/users"
BASE_WEATHER_URL = "https://api.weather.example.com/v2/current"
BASE_NOTIFY_URL = "https://api.notify.example.com/v1/send"


def get_user(user_id: str) -> dict:
    """Fetch user profile from the user API."""
    response = requests.get(f"{BASE_USER_URL}/{user_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def get_weather(city: str) -> dict:
    """Fetch current weather for a city."""
    response = requests.get(BASE_WEATHER_URL, params={"city": city}, timeout=10)
    response.raise_for_status()
    return response.json()


def send_notification(user_id: str, message: str) -> dict:
    """Send a notification to a user."""
    try:
        response = requests.post(
            BASE_NOTIFY_URL,
            json={"user_id": user_id, "message": message},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "timeout"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "message": "connection_error"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": str(e)}


def process_user_weather(user_id: str, city: str) -> dict:
    """Get user info and weather, then notify them."""
    user = get_user(user_id)
    weather = get_weather(city)
    msg = f"Hi {user.get('name', 'User')}, weather in {city}: {weather.get('temp', '?')}F"
    result = send_notification(user_id, msg)
    return {"user": user, "weather": weather, "notification": result}
