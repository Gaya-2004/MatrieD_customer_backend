import os
import sys
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models.user import User
from .models.restaurant import Restaurant
from .models.table import Table
from .utils.auth import hash_password


def seed_defaults(db: Session = None):
    """
    Seed default restaurant, admin, manager, cashier, and waiter accounts
    if they do not already exist.
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        # 1. Seed Restaurant 1 if missing
        rest = db.query(Restaurant).filter(Restaurant.id == 1).first()
        if not rest:
            rest = Restaurant(
                id=1,
                name="MaitreD Bistro",
                address="102 Luxury Boulevard, Central District",
                phone="+91 98765 43210"
            )
            db.add(rest)
            db.commit()
            print("[SEED] Created default restaurant: MaitreD Bistro (ID: 1)")

        # 2. Seed Default Users
        default_hash = hash_password("password123")
        users_to_seed = [
            {
                "email": "admin@maitred.com",
                "name": "Super Admin",
                "role": "SUPER_ADMIN",
                "restaurant_id": None,
                "phone": "9876543200",
                "is_approved": True,
            },
            {
                "email": "manager@maitred.com",
                "name": "MaitreD Manager",
                "role": "HOTEL_ADMIN",
                "restaurant_id": 1,
                "phone": "9876543201",
                "is_approved": True,
            },
            {
                "email": "cashier@maitred.com",
                "name": "Cashier Staff",
                "role": "CASHIER",
                "restaurant_id": 1,
                "phone": "9876543202",
                "is_approved": True,
            },
            {
                "email": "waiter_9876543210@maitred.internal",
                "name": "Rahul Kumar",
                "role": "WAITER",
                "restaurant_id": 1,
                "phone": "9876543210",
                "is_approved": True,
            },
            {
                "email": "waiter_9876543211@maitred.internal",
                "name": "Priya Sharma",
                "role": "WAITER",
                "restaurant_id": 1,
                "phone": "9876543211",
                "is_approved": True,
            },
        ]

        for u in users_to_seed:
            existing = db.query(User).filter(
                (User.email == u["email"]) | (User.phone == u["phone"])
            ).first()
            if not existing:
                new_user = User(
                    email=u["email"],
                    name=u["name"],
                    password_hash=default_hash,
                    role=u["role"],
                    restaurant_id=u["restaurant_id"],
                    phone=u["phone"],
                    is_active=True,
                    is_approved=u["is_approved"],
                )
                db.add(new_user)
                db.commit()
                print(f"[SEED] Created default user: {u['email']} ({u['role']})")

        # 3. Seed Tables if none exist
        table_count = db.query(Table).count()
        if table_count == 0:
            for i in range(1, 16):
                t = Table(
                    table_number=f"T-{i:02d}",
                    capacity=4 if i <= 10 else 6,
                    status="Vacant",
                    restaurant_id=1,
                )
                db.add(t)
            db.commit()
            print("[SEED] Created 15 default tables for Restaurant 1")

        # 4. Seed Default Customer 1 if missing
        from .models.customer import Customer
        cust = db.query(Customer).filter(Customer.id == 1).first()
        if not cust:
            cust = Customer(
                id=1,
                name="Test User(Testing Purpose only)",
                phone="+919876543210",
                email="guest@maitred.com",
                loyalty_points=50,
            )
            db.add(cust)
            db.commit()
            print("[SEED] Created default customer: Guest User (ID: 1)")

<<<<<<< HEAD
=======
        # 5. Seed Default Delivery Partner if missing
        from .models.delivery import DeliveryPartner
        rider = db.query(DeliveryPartner).filter(DeliveryPartner.phone == "9876543210").first()
        if not rider:
            rider = DeliveryPartner(
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
            db.add(rider)
            print("[SEED] Created default rider: Ramesh Kumar (9876543210)")

        db.commit()
>>>>>>> bcf5baf (feat(rider): add documents, bank details, delivery status earnings, and model improvements)
        print("[SEED] Database seeding check completed.")
    except Exception as e:
        db.rollback()
        print(f"[SEED] Seeding error: {e}")
    finally:
        if should_close:
            db.close()


if __name__ == "__main__":
    seed_defaults()

