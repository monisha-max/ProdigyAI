"""
Google Maps Platform — via REST API as ADK FunctionTools.
Uses the Maps Places API and Directions API directly.
More reliable than remote MCP in local/FastAPI async contexts.
"""

import os
import json
import urllib.request
import urllib.parse
import dotenv

dotenv.load_dotenv()
MAPS_API_KEY = os.getenv("MAPS_API_KEY", "")


def search_places(
    query: str,
    location_bias: str = "",
) -> dict:
    """Search for places using Google Maps. Use this to find restaurants, venues,
    coffee shops, coworking spaces, or any business near a location.

    Args:
        query: What to search for (e.g., "coffee shops near downtown LA", "restaurants near Times Square").
        location_bias: Optional location to bias results toward (e.g., "San Francisco" or "37.7749,-122.4194").

    Returns:
        A dict with up to 5 place results including name, address, rating, and types.
    """
    if not MAPS_API_KEY:
        return {"error": "Maps API key not configured", "results": []}

    search_text = f"{query} {location_bias}".strip()
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": MAPS_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.types,places.googleMapsUri",
    }
    body = json.dumps({"textQuery": search_text, "maxResultCount": 5}).encode()

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        results = []
        for place in data.get("places", []):
            results.append({
                "name": place.get("displayName", {}).get("text", "Unknown"),
                "address": place.get("formattedAddress", ""),
                "rating": place.get("rating", "N/A"),
                "reviews": place.get("userRatingCount", 0),
                "type": ", ".join(place.get("types", [])[:3]),
                "maps_url": place.get("googleMapsUri", ""),
            })

        return {
            "query": search_text,
            "results_count": len(results),
            "results": results,
        }
    except Exception as e:
        return {"error": str(e), "query": search_text, "results": []}


def get_directions(
    origin: str,
    destination: str,
    mode: str = "driving",
) -> dict:
    """Get directions and travel time between two locations using Google Maps.

    Args:
        origin: Starting address or place name.
        destination: Ending address or place name.
        mode: Travel mode — driving, walking, bicycling, or transit.

    Returns:
        A dict with distance, duration, and a Google Maps directions URL.
    """
    if not MAPS_API_KEY:
        return {"error": "Maps API key not configured"}

    params = urllib.parse.urlencode({
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "key": MAPS_API_KEY,
    })
    url = f"https://maps.googleapis.com/maps/api/directions/json?{params}"

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())

        if data.get("status") != "OK" or not data.get("routes"):
            return {"error": f"No route found: {data.get('status')}", "origin": origin, "destination": destination}

        route = data["routes"][0]["legs"][0]
        maps_url = f"https://www.google.com/maps/dir/{urllib.parse.quote(origin)}/{urllib.parse.quote(destination)}"

        return {
            "origin": origin,
            "destination": destination,
            "distance": route.get("distance", {}).get("text", "Unknown"),
            "duration": route.get("duration", {}).get("text", "Unknown"),
            "mode": mode,
            "maps_url": maps_url,
        }
    except Exception as e:
        return {"error": str(e), "origin": origin, "destination": destination}
