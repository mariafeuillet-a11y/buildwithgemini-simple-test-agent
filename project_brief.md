# My agent: smart-pantry-agent
One-liner: A conversational pantry and recipe concierge that helps home cooks manage their pantry inventory and discover grounded recipe recommendations.

Tool coverage:
- Memory: Remembers user dietary preferences, allergies, and cooking goals.
- Tools: Reads and writes the Firestore `pantry_items` collection (e.g. search pantry items, add/update item quantity, remove items).
- Catalog/UI: Catalog of pantry inventory items rendered as cards or structured lists.
- Image gen: Generates visual dish previews for recommended recipes.
- Sandbox: Calculates required ingredient quantities and scaling for recipes.

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch: Firestore database, code sandbox for ingredient scaling calculations
