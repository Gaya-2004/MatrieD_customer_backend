import os
import json
from datetime import datetime, timedelta
from app.db import SessionLocal
from app.models.delivery import DeliveryPartner, DeliveryAssignment, RiderDocument, RiderBankDetail
from app.models.order import Order, OrderItem
from app.models.restaurant import Restaurant
from app.models.menu import MenuItem
from app.utils.auth import hash_password

def seed_sample_riders():
    db = SessionLocal()
    try:
        # Check restaurant
        restaurant = db.query(Restaurant).first()
        if not restaurant:
            restaurant = Restaurant(
                name="MaitreD Gourmet Bistro",
                address="100 MG Road, Bangalore, Karnataka",
                phone="+91 98765 43210",
                latitude=12.9716,
                longitude=77.5946,
                tax_rate=5.0,
                packaging_charge=20.0,
            )
            db.add(restaurant)
            db.commit()
            db.refresh(restaurant)

        # 1. Rider 1: Fully registered and active
        p1 = db.query(DeliveryPartner).filter(DeliveryPartner.phone == "9876543210").first()
        if not p1:
            p1 = DeliveryPartner(
                name="Ramesh Kumar",
                phone="9876543210",
                email="ramesh.rider@maitred.com",
                vehicle_type="Bike",
                vehicle_number="KA01AB1234",
                vehicle_brand="Honda",
                vehicle_model="Activa 6G",
                fuel_type="Petrol",
                vehicle_color="Black",
                rating=4.9,
                total_ratings=32,
                total_rides=58,
                is_online=True,
                is_available=True,
                is_active=True,
                current_latitude=12.9716,
                current_longitude=77.5946,
                password_hash=hash_password("Password@123")
            )
            db.add(p1)
            db.commit()
            db.refresh(p1)
            print(f"[OK] Seeded registered rider: {p1.name} (Phone: 9876543210, Password: Password@123)")

            # Seed Rider Documents
            doc = RiderDocument(
                rider_id=p1.id,
                document_type="license",
                document_number="DL-0420110149632",
                document_url="https://images.unsplash.com/photo-1544717305-2782549b5136?w=400",
                verification_status="VERIFIED"
            )
            db.add(doc)

            # Seed Rider Bank Details
            bank = RiderBankDetail(
                rider_id=p1.id,
                account_name="Ramesh Kumar",
                account_number="987654321098",
                ifsc_code="HDFC0001234",
                bank_name="HDFC Bank"
            )
            db.add(bank)
            db.commit()
        else:
            print(f"Rider already exists: {p1.name}")

        # 2. Rider 2: Pre-onboarded rider for registration testing
        p2 = db.query(DeliveryPartner).filter(DeliveryPartner.phone == "9876543212").first()
        if not p2:
            p2 = DeliveryPartner(
                name="Mahesh Sharma",
                phone="9876543212",
                email="mahesh.rider@maitred.com",
                vehicle_type="Motorcycle",
                vehicle_number="KA02CD5678",
                vehicle_brand="Hero",
                vehicle_model="Splendor Plus",
                fuel_type="Petrol",
                vehicle_color="Blue",
                rating=5.0,
                total_ratings=5,
                total_rides=12,
                is_online=False,
                is_available=False,
                is_active=True,
                password_hash=None  # Can register or set password!
            )
            db.add(p2)
            db.commit()
            print("[OK] Seeded pre-onboarded rider for registration: Mahesh Sharma (Phone: 9876543212)")

        # 3. Create Sample Delivery Orders if none exist
        menu_items = db.query(MenuItem).all()
        existing_orders = db.query(Order).filter(Order.order_type == "DELIVERY").count()
        if existing_orders == 0 and menu_items:
            address_snapshot = {
                "full_address": "Flat 301, Brigade Residency, Indiranagar, Bangalore",
                "flat_house_no": "301",
                "building_apartment_name": "Brigade Residency",
                "city": "Bangalore",
                "latitude": 12.9784,
                "longitude": 77.6408,
                "contact_name": "Priya Sharma",
                "contact_phone": "9876500001"
            }

            sample_order = Order(
                restaurant_id=restaurant.id,
                table_id=None,
                status="CONFIRMED",
                payment_method="ONLINE",
                payment_status="COMPLETED",
                order_type="DELIVERY",
                total_amount=540.0,
                customer_phone="9876500001",
                customer_name="Priya Sharma",
                delivery_status="READY_FOR_PICKUP",
                delivery_address_snapshot=json.dumps(address_snapshot),
                delivery_instructions="Please ring the doorbell and leave at door",
                delivery_fee=40.0,
                packaging_fee=20.0,
                gst_amount=24.0,
                tip_amount=30.0,
                order_source="CUSTOMER_APP"
            )
            db.add(sample_order)
            db.commit()
            db.refresh(sample_order)

            # Add order items
            for item in menu_items[:2]:
                oi = OrderItem(
                    order_id=sample_order.id,
                    menu_item_id=item.id,
                    quantity=1.0,
                    price=item.price,
                    status="READY"
                )
                db.add(oi)

            # Create an assignment available for acceptance or assigned
            assignment = DeliveryAssignment(
                order_id=sample_order.id,
                rider_id=p1.id,
                status="ASSIGNED",
                assigned_at=datetime.utcnow()
            )
            db.add(assignment)
            db.commit()
            print(f"[OK] Seeded sample delivery order #{sample_order.id} with assignment #{assignment.id}")

        print("Rider and delivery seed completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding riders: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_sample_riders()
