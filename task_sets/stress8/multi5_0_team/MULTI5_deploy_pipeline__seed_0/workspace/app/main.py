"""Main application entry point for webapp."""
import os
from app.models import DatabaseConnection
from app.utils import format_response, validate_input


def create_app(config=None):
    """Create and configure the application instance with default settings for webapp."""
    db = DatabaseConnection(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "8080")))
    return {"db": db, "config": config or {}}


def handle_request(app, request_data):
    """Handle an incoming request, validate it, process through the database, and return a formatted response."""
    if not validate_input(request_data):
        return format_response(error="Invalid input data provided to the webapp service endpoint")
    result = app["db"].query(request_data.get("query", "SELECT 1"))
    return format_response(data=result, status="success")
