import base64
import datetime
import json
import os
import time
import urllib.parse
import urllib.request

import google.auth
from google import genai
from google.adk.tools import ToolContext
from google.cloud import firestore, storage
from google.genai import types

# Load local .env file if present
def load_local_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k, v)

load_local_env()

# IMPORTANT: Hardcode project ID & bucket name to prevent resolution issues
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-03-faf83d47ec83"
BUCKET_NAME = "smart-pantry-images-qwiklabs-gcp-03-faf83d47ec83"

def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the explicit project ID and scopes."""
    creds, _ = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/datastore",
        ]
    )
    return firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=creds)


def get_pantry_items(category: str = "") -> str:
    """Gets items from the pantry database.

    Args:
        category: Optional category filter (e.g. 'Grains', 'Produce', 'Dairy', 'Canned Goods').

    Returns:
        A string formatted list of pantry items with their quantities and units.
    """
    db = get_firestore_client()
    collection_ref = db.collection("pantry_items")

    if category:
        query = collection_ref.where("category", "==", category)
        docs = query.stream()
    else:
        docs = collection_ref.stream()

    items = []
    for doc in docs:
        data = doc.to_dict()
        items.append(
            f"- {data.get('name', doc.id)} (ID: {doc.id}): {data.get('quantity', 0)} {data.get('unit', 'units')} "
            f"[Category: {data.get('category', 'Uncategorized')}, Expires: {data.get('expiration_date', 'N/A')}]"
        )

    if not items:
        if category:
            return f"No pantry items found for category '{category}'."
        return "Your pantry is currently empty."

    return "Current Pantry Items:\n" + "\n".join(items)


def add_pantry_item(
    item_id: str,
    name: str,
    category: str,
    quantity: float,
    unit: str,
    expiration_date: str = "",
) -> str:
    """Adds a new item or updates an existing item in the pantry database.

    Args:
        item_id: Unique string identifier for the item (e.g., 'milk', 'flour').
        name: Human-readable item name (e.g., 'Whole Milk').
        category: Category of item (e.g., 'Dairy', 'Grains', 'Produce').
        quantity: Numerical quantity available.
        unit: Unit of measurement (e.g., 'gallons', 'lbs', 'cans').
        expiration_date: Optional expiration date string (YYYY-MM-DD).

    Returns:
        Confirmation message of item addition or update.
    """
    db = get_firestore_client()
    item_data = {
        "id": item_id.lower().replace(" ", "_"),
        "name": name,
        "category": category,
        "quantity": float(quantity),
        "unit": unit,
        "expiration_date": expiration_date,
    }

    doc_ref = db.collection("pantry_items").document(item_data["id"])
    doc_ref.set(item_data, merge=True)
    return f"Successfully saved '{name}' ({quantity} {unit}) to pantry items."


def use_pantry_item(item_id: str, quantity_used: float) -> str:
    """Decrements the quantity of a pantry item after using it in a recipe.

    Args:
        item_id: Unique string identifier for the item (e.g., 'pasta', 'tomato_sauce').
        quantity_used: Amount of the item consumed.

    Returns:
        Status message with updated quantity.
    """
    db = get_firestore_client()
    clean_id = item_id.lower().replace(" ", "_")
    doc_ref = db.collection("pantry_items").document(clean_id)
    doc = doc_ref.get()

    if not doc.exists:
        return f"Item '{item_id}' not found in pantry."

    data = doc.to_dict()
    current_qty = float(data.get("quantity", 0))
    new_qty = max(0.0, current_qty - float(quantity_used))

    doc_ref.update({"quantity": new_qty})
    return f"Updated {data.get('name', item_id)}: used {quantity_used} {data.get('unit', '')}. Remaining: {new_qty} {data.get('unit', '')}."


def generate_grocery_shopping_list(threshold_days: int = 30) -> str:
    """Scans Firestore pantry items and generates a grocery shopping list for low stock or expiring items.

    Args:
        threshold_days: Number of days to check for upcoming item expiration (default: 30).

    Returns:
        A formatted grocery shopping list detailing items that need restocking or replacing.
    """
    db = get_firestore_client()
    docs = db.collection("pantry_items").stream()

    low_stock = []
    expiring_soon = []

    today_str = datetime.date.today().isoformat()
    target_date = (datetime.date.today() + datetime.timedelta(days=threshold_days)).isoformat()

    for doc in docs:
        data = doc.to_dict()
        name = data.get("name", doc.id)
        qty = float(data.get("quantity", 0))
        unit = data.get("unit", "")
        exp_date = data.get("expiration_date", "")

        if qty <= 1.0:
            low_stock.append(f"- {name}: only {qty} {unit} remaining")

        if exp_date and today_str <= exp_date <= target_date:
            expiring_soon.append(f"- {name}: expires on {exp_date} (current stock: {qty} {unit})")

    lines = ["🛒 **Generated Grocery Shopping List**"]
    if low_stock:
        lines.append("\n**Low Stock Items (Restock Needed):**")
        lines.extend(low_stock)
    if expiring_soon:
        lines.append(f"\n**Expiring Soon (Within {threshold_days} days):**")
        lines.extend(expiring_soon)

    if not low_stock and not expiring_soon:
        return "Your pantry is well-stocked! No items are low on stock or expiring soon."

    return "\n".join(lines)


def search_online_recipes(query: str) -> str:
    """Searches for real online recipes matching a dish name or main ingredient via TheMealDB API.

    Args:
        query: Recipe query or main ingredient to search for (e.g. 'pasta', 'chicken', 'curry').

    Returns:
        Formatted summary of matching recipes with ingredients, preparation steps, and dish photo URLs.
    """
    api_key = os.getenv("THEMEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={urllib.parse.quote(query)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

        meals = data.get("meals")
        if not meals:
            return f"No recipes found on TheMealDB matching '{query}'."

        results = []
        for meal in meals[:3]:
            name = meal.get("strMeal")
            category = meal.get("strCategory")
            area = meal.get("strArea")
            instructions = meal.get("strInstructions", "")[:200] + "..."
            thumb = meal.get("strMealThumb")

            ingredients = []
            for i in range(1, 21):
                ing = meal.get(f"strIngredient{i}")
                measure = meal.get(f"strMeasure{i}")
                if ing and ing.strip():
                    ingredients.append(f"{measure.strip() if measure else ''} {ing.strip()}".strip())

            ing_str = ", ".join(ingredients[:8])
            results.append(
                f"🍳 **{name}** ({area} {category})\n"
                f"- Ingredients: {ing_str}\n"
                f"- Instructions: {instructions}\n"
                f"- Photo: {thumb}"
            )

        return f"Found {len(results)} recipe(s) for '{query}':\n\n" + "\n\n".join(results)

    except Exception as e:
        return f"Error fetching recipes from TheMealDB: {e}"


def geocode_address(address: str) -> str:
    """Converts a street address or location name into geographic coordinates (latitude and longitude).

    Args:
        address: The location or address string (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA' or 'San Francisco, CA').

    Returns:
        Formatted string containing the formatted address and latitude/longitude coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY is not set in environment variables."

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return f"Geocoding failed for address '{address}': {data.get('error_message', data.get('status'))}"

        result = data["results"][0]
        formatted_address = result.get("formatted_address")
        location = result.get("geometry", {}).get("location", {})
        lat = location.get("lat")
        lng = location.get("lng")

        return f"Location: {formatted_address}\nCoordinates: Latitude {lat}, Longitude {lng}"

    except Exception as e:
        return f"Error executing Geocoding request: {e}"


def find_nearby_places(place_type: str, latitude: float, longitude: float, radius_meters: float = 2000.0) -> str:
    """Finds nearby places of a given type around a geographic location using Places API (New).

    Args:
        place_type: The type of place or query (e.g. 'grocery_store', 'supermarket', 'bakery', 'restaurant').
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        radius_meters: Radius in meters to search within (default: 2000.0).

    Returns:
        Formatted string listing matching nearby places with name, address, and coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY is not set in environment variables."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }

    clean_type = place_type.lower().strip().replace(" ", "_")
    valid_type = clean_type if clean_type in ["grocery_store", "supermarket", "bakery", "restaurant", "store"] else "grocery_store"

    payload = {
        "includedTypes": [valid_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude)
                },
                "radius": float(radius_meters)
            }
        }
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

        places = data.get("places", [])
        if not places:
            return f"No nearby places found for type '{place_type}' within {radius_meters}m."

        results = []
        for p in places:
            name = p.get("displayName", {}).get("text", "Unknown Name")
            address = p.get("formattedAddress", "No address")
            loc = p.get("location", {})
            results.append(
                f"- **{name}**\n"
                f"  Address: {address}\n"
                f"  Location: Latitude {loc.get('latitude')}, Longitude {loc.get('longitude')}"
            )

        return f"Found {len(results)} nearby place(s):\n\n" + "\n\n".join(results)

    except Exception as e:
        return f"Error executing Places searchNearby request: {e}"


def generate_pantry_item_image(item_name: str, tool_context: ToolContext) -> str:
    """Generates an image of a pantry item or dish using gemini-3.1-flash-lite-image model in global region, saves as artifact, and uploads to public Cloud Storage.

    Args:
        item_name: Name of the pantry item or dish to generate an image for (e.g., 'pasta', 'tomato sauce').
        tool_context: ToolContext instance provided automatically by ADK.

    Returns:
        The public HTTPS URL of the uploaded image on Cloud Storage.
    """
    clean_name = item_name.lower().replace(" ", "_")
    prompt = f"A high quality professional food photograph of {item_name}, appetizing and beautifully arranged."

    try:
        # 1. Generate image using gemini-3.1-flash-lite-image in global region
        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global"
        )
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        image_bytes = None
        for candidate in getattr(response, "candidates", []):
            for part in candidate.content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    break

        if not image_bytes:
            return f"Failed to generate image bytes for '{item_name}'."

        # 2. Save artifact using tool_context.save_artifact
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        tool_context.save_artifact(filename=f"{clean_name}.jpg", artifact=artifact_part)

        # 3. Upload image bytes directly to GCS bucket (no local file writing)
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        object_name = f"items/{clean_name}_{int(time.time())}.jpg"
        blob = bucket.blob(object_name)
        blob.upload_from_string(image_bytes, content_type="image/jpeg")

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{object_name}"
        return f"Successfully generated image for '{item_name}'. Saved artifact '{clean_name}.jpg' and uploaded to public GCS: {public_url}"

    except Exception as e:
        return f"Error generating or uploading image for '{item_name}': {e}"


def generate_pantry_item_video(item_name: str, tool_context: ToolContext) -> str:
    """Generates a short video of a pantry item or dish using gemini-omni-flash-preview model in global region, saves as artifact, and uploads to public Cloud Storage.

    Args:
        item_name: Name of the pantry item or dish to generate a video for (e.g., 'pasta', 'pan-seared steak', 'pancakes').
        tool_context: ToolContext instance provided automatically by ADK.

    Returns:
        The public HTTPS URL of the uploaded video on Cloud Storage.
    """
    clean_name = item_name.lower().replace(" ", "_")
    prompt = f"Generate a short video of {item_name} being cooked or served in a kitchen."

    try:
        # 1. Generate video using gemini-omni-flash-preview via Interactions API in global region
        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global"
        )
        response = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt
        )

        vid = getattr(response, "output_video", None)
        if not vid or not getattr(vid, "data", None):
            return f"Failed to generate video data for '{item_name}'."

        raw_data = vid.data
        if isinstance(raw_data, str):
            video_bytes = base64.b64decode(raw_data)
        else:
            video_bytes = raw_data

        mime_type = getattr(vid, "mime_type", "video/mp4") or "video/mp4"

        # 2. Save artifact using tool_context.save_artifact so it shows up in Playground Artifacts panel
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=f"{clean_name}.mp4", artifact=artifact_part)

        # 3. Upload video bytes directly to public GCS bucket (no local file writing)
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        object_name = f"videos/{clean_name}_{int(time.time())}.mp4"
        blob = bucket.blob(object_name)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{object_name}"
        return f"Successfully generated video for '{item_name}'. Saved artifact '{clean_name}.mp4' and uploaded to public GCS: {public_url}"

    except Exception as e:
        return f"Error generating or uploading video for '{item_name}': {e}"

