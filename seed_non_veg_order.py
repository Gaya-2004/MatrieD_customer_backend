import os, sys, json
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv('d:/TECH WIZARD FOLDER-INTERN/matrieD_customer_backend/.env', override=True)
sys.path.append('d:/TECH WIZARD FOLDER-INTERN/matrieD_customer_backend')

from app.db import SessionLocal
from app.models import (
    DeliveryPartner, Restaurant, MenuItem, MenuCategory, Order, OrderItem
)
from app.models.delivery import DeliveryAssignment, DeliveryStatusHistory

def create_non_veg_delivery_order():
    db = SessionLocal()
    try:
        # 1. Verify Rider 2
        rider = db.query(DeliveryPartner).filter(DeliveryPartner.id == 2).first()
        if not rider:
            raise Exception("Rider ID 2 ('Maitred Rider 1') not found.")
        print(f"Rider: {rider.name} (ID: {rider.id}), Online: {rider.is_online}, Available: {rider.is_available}")

        # Ensure rider is marked available and online
        rider.is_online = True
        rider.is_available = True
        rider.is_active = True
        db.commit()

        # 2. Verify Restaurant 2 (MGR Nagar)
        restaurant = db.query(Restaurant).filter(Restaurant.id == 2).first()
        if not restaurant:
            raise Exception("Restaurant ID 2 not found.")
        print(f"Restaurant: {restaurant.name} (ID: {restaurant.id}) at {restaurant.address}")

        # 3. Ensure MenuCategory for Non-Veg exists
        non_veg_cat = db.query(MenuCategory).filter(MenuCategory.name == "Non-Veg Specials (MGR Nagar)").first()
        if not non_veg_cat:
            non_veg_cat = MenuCategory(
                restaurant_id=restaurant.id,
                name="Non-Veg Specials (MGR Nagar)",
                description="Special Non-Veg Delicacies and Biryani"
            )
            db.add(non_veg_cat)
            db.commit()
            db.refresh(non_veg_cat)
            print(f"Created Category: {non_veg_cat.name} (ID: {non_veg_cat.id})")
        else:
            print(f"Category exists: {non_veg_cat.name} (ID: {non_veg_cat.id})")

        # 4. Ensure Non-Veg Menu Items exist
        chicken_biryani = db.query(MenuItem).filter(
            MenuItem.restaurant_id == restaurant.id,
            MenuItem.name == "Hyderabadi Chicken Dum Biryani"
        ).first()

        if not chicken_biryani:
            chicken_biryani = MenuItem(
                restaurant_id=restaurant.id,
                category_id=non_veg_cat.id,
                name="Hyderabadi Chicken Dum Biryani",
                description="Fragrant basmati rice slow-cooked with spiced chicken pieces, saffron, and mint.",
                price=240.00,
                food_type="NON_VEG",
                is_available=True,
                is_deleted=False,
                quantity=100
            )
            db.add(chicken_biryani)
            db.commit()
            db.refresh(chicken_biryani)
            print(f"Created MenuItem: {chicken_biryani.name} (ID: {chicken_biryani.id}) - Rs. {chicken_biryani.price}")
        else:
            chicken_biryani.food_type = "NON_VEG"
            db.commit()
            print(f"MenuItem exists: {chicken_biryani.name} (ID: {chicken_biryani.id})")

        pepper_chicken = db.query(MenuItem).filter(
            MenuItem.restaurant_id == restaurant.id,
            MenuItem.name == "Chettinad Pepper Chicken Fry"
        ).first()

        if not pepper_chicken:
            pepper_chicken = MenuItem(
                restaurant_id=restaurant.id,
                category_id=non_veg_cat.id,
                name="Chettinad Pepper Chicken Fry",
                description="Spicy tender boneless chicken tossed with roasted black pepper and curry leaves.",
                price=190.00,
                food_type="NON_VEG",
                is_available=True,
                is_deleted=False,
                quantity=100
            )
            db.add(pepper_chicken)
            db.commit()
            db.refresh(pepper_chicken)
            print(f"Created MenuItem: {pepper_chicken.name} (ID: {pepper_chicken.id}) - Rs. {pepper_chicken.price}")
        else:
            pepper_chicken.food_type = "NON_VEG"
            db.commit()
            print(f"MenuItem exists: {pepper_chicken.name} (ID: {pepper_chicken.id})")

        # 5. Delivery Address for Customer (Nandanam / Saidapet area)
        delivery_addr_data = {
            "contact_name": "Kavitha Sundaram",
            "contact_phone": "9840987654",
            "address_line": "Door No. 18, 2nd Main Road, CIT Nagar West, Nandanam",
            "full_address": "Door No. 18, 2nd Main Road, CIT Nagar West, Nandanam, Chennai - 600035",
            "landmark": "Opposite Nandanam Arts College Grounds",
            "instructions": "Ring doorbell on 2nd floor. Opposite park entrance.",
            "latitude": 13.0298,
            "longitude": 80.2312
        }

        # Calculation
        biryani_qty = 1.0
        biryani_price = float(chicken_biryani.price) # 240.0
        chicken_qty = 1.0
        chicken_price = float(pepper_chicken.price)  # 190.0
        subtotal = (biryani_price * biryani_qty) + (chicken_price * chicken_qty) # 430.0
        delivery_fee = 60.00
        packaging_fee = 25.00
        gst_amount = round(subtotal * 0.05, 2) # 21.50
        tip_amount = 0.00
        total_amount = round(subtotal + delivery_fee + packaging_fee + gst_amount + tip_amount, 2) # 536.50

        # 6. Create Order
        now = datetime.utcnow()
        new_order = Order(
            restaurant_id=restaurant.id,
            status="CONFIRMED",
            payment_method="UPI",
            payment_status="PAID",
            order_type="DELIVERY",
            total_amount=total_amount,
            customer_name=delivery_addr_data["contact_name"],
            customer_phone=delivery_addr_data["contact_phone"],
            delivery_address_snapshot=json.dumps(delivery_addr_data),
            delivery_instructions=delivery_addr_data["instructions"],
            delivery_status="RIDER_ASSIGNED",
            delivery_fee=delivery_fee,
            packaging_fee=packaging_fee,
            gst_amount=gst_amount,
            tip_amount=tip_amount,
            order_source="CUSTOMER_APP",
            created_at=now,
            updated_at=now
        )
        db.add(new_order)
        db.flush() # gets new_order.id

        # 7. Add Order Items
        oi1 = OrderItem(
            order_id=new_order.id,
            menu_item_id=chicken_biryani.id,
            quantity=biryani_qty,
            price=biryani_price,
            status="CONFIRMED"
        )
        oi2 = OrderItem(
            order_id=new_order.id,
            menu_item_id=pepper_chicken.id,
            quantity=chicken_qty,
            price=chicken_price,
            status="CONFIRMED"
        )
        db.add_all([oi1, oi2])
        db.flush()

        # 8. Create Delivery Assignment
        assignment = DeliveryAssignment(
            order_id=new_order.id,
            rider_id=rider.id,
            status="ASSIGNED",
            assigned_at=now,
            created_at=now,
            updated_at=now
        )
        db.add(assignment)
        db.flush()

        # 9. Log initial status history
        history = DeliveryStatusHistory(
            order_id=new_order.id,
            delivery_assignment_id=assignment.id,
            rider_id=rider.id,
            status="RIDER_ASSIGNED",
            notes="New delivery with Non-Veg dishes dispatched to Maitred Rider 1",
            created_at=now
        )
        db.add(history)
        db.commit()

        display_id = f"ORD-{str(new_order.id).zfill(6)}"
        print("----------------------------------------------------")
        print("SUCCESSFULLY CREATED NON-VEG DELIVERY ORDER!")
        print(f"Order ID: {new_order.id}")
        print(f"Display ID: {display_id}")
        print(f"Assignment ID: {assignment.id}")
        print(f"Status: ASSIGNED")
        print(f"Assigned to: {rider.name} (Rider ID: {rider.id})")
        print(f"Restaurant: {restaurant.name}")
        print(f"Customer: {new_order.customer_name} ({new_order.customer_phone})")
        print(f"Delivery Address: {delivery_addr_data['address_line']}")
        print(f"Non-Veg Items: {chicken_biryani.name} (Rs. {biryani_price}), {pepper_chicken.name} (Rs. {chicken_price})")
        print(f"Total Amount: Rs. {total_amount}")
        print("----------------------------------------------------")
        return new_order.id, assignment.id

    except Exception as e:
        db.rollback()
        print(f"Error creating order: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    create_non_veg_delivery_order()
