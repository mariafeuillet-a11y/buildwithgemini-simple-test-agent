#!/usr/bin/env python3
import google.auth
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-faf83d47ec83"

def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}")
    creds, _ = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/datastore",
        ]
    )
    db = firestore.Client(project=PROJECT_ID, credentials=creds)

    pantry_items = [
        {
            "id": "pasta",
            "name": "Pasta",
            "category": "Grains",
            "quantity": 2.0,
            "unit": "boxes",
            "expiration_date": "2026-12-31"
        },
        {
            "id": "tomato_sauce",
            "name": "Tomato Sauce",
            "category": "Canned Goods",
            "quantity": 4.0,
            "unit": "cans",
            "expiration_date": "2026-11-15"
        },
        {
            "id": "olive_oil",
            "name": "Olive Oil",
            "category": "Oils & Condiments",
            "quantity": 1.0,
            "unit": "bottle",
            "expiration_date": "2027-05-01"
        },
        {
            "id": "garlic",
            "name": "Garlic",
            "category": "Produce",
            "quantity": 3.0,
            "unit": "cloves",
            "expiration_date": "2026-10-20"
        },
        {
            "id": "parmesan",
            "name": "Parmesan Cheese",
            "category": "Dairy",
            "quantity": 1.0,
            "unit": "block",
            "expiration_date": "2026-10-30"
        }
    ]

    collection_ref = db.collection("pantry_items")
    for item in pantry_items:
        doc_id = item["id"]
        collection_ref.document(doc_id).set(item)
        print(f"Seeded pantry_item: {doc_id} -> {item['name']} ({item['quantity']} {item['unit']})")

    print("Firestore seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
