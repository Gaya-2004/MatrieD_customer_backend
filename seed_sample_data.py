from app.db import SessionLocal
from app.models.restaurant import Restaurant
from app.models.menu import MenuCategory, MenuItem
from app.models.table import Table
from app.models.customer import Customer, CustomerAddress

def seed_sample_data():
    db = SessionLocal()
    try:
        # 1. Restaurant
        restaurant = db.query(Restaurant).first()
        if not restaurant:
            restaurant = Restaurant(
                name="MaitreD Gourmet Bistro",
                address="100 MG Road, Bangalore, Karnataka",
                phone="+91 98765 43210",
                latitude=12.9716,
                longitude=77.5946,
                tax_rate=5.0,
                service_charge=0.0,
                packaging_charge=20.0,
                opening_time="09:00",
                closing_time="23:00",
                auto_print_bills=1,
                order_notifications=1
            )
            db.add(restaurant)
            db.commit()
            db.refresh(restaurant)
            print(f"Created restaurant: {restaurant.name} (ID: {restaurant.id})")
        else:
            print(f"Restaurant already exists: {restaurant.name} (ID: {restaurant.id})")

        # Associate all tables with restaurant_id
        db.query(Table).update({Table.restaurant_id: restaurant.id})
        db.commit()

        # 1b. Guest Customer & Address
        guest_customer = db.query(Customer).filter(Customer.id == 1).first()
        if not guest_customer:
            guest_customer = Customer(
                id=1,
                name="Guest User",
                phone="+919876543210",
                email="guest@maitred.com",
                loyalty_points=100
            )
            db.add(guest_customer)
            db.commit()
            db.refresh(guest_customer)
            print(f"Created customer: {guest_customer.name} (ID: {guest_customer.id})")
        else:
            print(f"Customer already exists: {guest_customer.name} (ID: {guest_customer.id})")

        guest_addr = db.query(CustomerAddress).filter(CustomerAddress.customer_id == guest_customer.id).first()
        if not guest_addr:
            guest_addr = CustomerAddress(
                customer_id=guest_customer.id,
                address_type="Home",
                flat_house_no="Flat 402",
                building_apartment_name="Prestige Towers",
                full_address="Prestige Towers, MG Road, Bangalore",
                city="Bangalore",
                state="Karnataka",
                pincode="560001",
                contact_name="Guest User",
                contact_phone="+919876543210",
                latitude=12.9716,
                longitude=77.5946,
                is_default=True,
                is_active=True
            )
            db.add(guest_addr)
            db.commit()
            print("Created default address for Guest User")

        # 2. Categories & Items
        catalog = [
            {
                "category": "Starters & Appetizers",
                "description": "Crispy, savory appetizers and finger foods",
                "items": [
                    {"name": "Paneer Tikka", "price": 240.0, "description": "Tender cottage cheese marinated in spiced yogurt and roasted in tandoor.", "code": "APP-01"},
                    {"name": "Crispy Corn Chili Pepper", "price": 190.0, "description": "Golden crispy sweet corn tossed with bell peppers and spring onion.", "code": "APP-02"},
                    {"name": "Chicken Tikka Kebab", "price": 280.0, "description": "Juicy chicken cubes marinated with aromatic spices and grilled.", "code": "APP-03"},
                    {"name": "Veg Spring Rolls", "price": 170.0, "description": "Crispy rolls filled with shredded vegetables, served with sweet chili sauce.", "code": "APP-04"},
                ]
            },
            {
                "category": "Biryanis & Rice",
                "description": "Fragrant dum biryanis and seasoned rice",
                "items": [
                    {"name": "Hyderabadi Chicken Dum Biryani", "price": 320.0, "description": "Slow-cooked basmati rice layered with spicy succulent chicken and saffron.", "code": "BIR-01"},
                    {"name": "Special Paneer Dum Biryani", "price": 270.0, "description": "Aromatic basmati rice cooked with fresh paneer cubes and whole spices.", "code": "BIR-02"},
                    {"name": "Mutton Dum Biryani", "price": 420.0, "description": "Rich, tender bone-in mutton pieces dum cooked with fragrant spices.", "code": "BIR-03"},
                    {"name": "Jeera Rice", "price": 150.0, "description": "Steamed premium basmati rice tempered with roasted cumin seeds and ghee.", "code": "RCE-01"},
                ]
            },
            {
                "category": "Main Course",
                "description": "Rich curries and signature gravies",
                "items": [
                    {"name": "Butter Chicken", "price": 340.0, "description": "Smoked tandoori chicken simmered in creamy tomato and cashew butter sauce.", "code": "CUR-01"},
                    {"name": "Paneer Butter Masala", "price": 290.0, "description": "Soft paneer cubes in a silky, mildly sweet and spiced tomato butter gravy.", "code": "CUR-02"},
                    {"name": "Dal Makhani", "price": 230.0, "description": "Overnight slow-cooked black lentils finished with cream and butter.", "code": "CUR-03"},
                    {"name": "Kadai Chicken", "price": 330.0, "description": "Chicken pieces cooked with freshly ground kadai spices, capsicum and onions.", "code": "CUR-04"},
                ]
            },
            {
                "category": "Breads",
                "description": "Freshly baked Indian breads from the tandoor",
                "items": [
                    {"name": "Garlic Butter Naan", "price": 60.0, "description": "Tandoor baked flatbread brushed with garlic butter.", "code": "BRD-01"},
                    {"name": "Butter Naan", "price": 50.0, "description": "Classic leavened bread layered with melted butter.", "code": "BRD-02"},
                    {"name": "Tandoori Roti", "price": 30.0, "description": "Whole wheat bread baked crisp in traditional clay oven.", "code": "BRD-03"},
                ]
            },
            {
                "category": "Desserts & Beverages",
                "description": "Sweet treats and cooling refreshments",
                "items": [
                    {"name": "Gulab Jamun (2 pcs)", "price": 90.0, "description": "Warm milk-solid dumplings soaked in rose flavored sugar syrup.", "code": "DES-01"},
                    {"name": "Rasmalai (2 pcs)", "price": 120.0, "description": "Soft cottage cheese patties soaked in thickened saffron cardamom milk.", "code": "DES-02"},
                    {"name": "Mango Lassi", "price": 110.0, "description": "Thick chilled yogurt smoothie blended with ripe alphonso mango puree.", "code": "BEV-01"},
                    {"name": "Fresh Lime Soda", "price": 70.0, "description": "Refreshing sparkling lime soda (Sweet & Salt).", "code": "BEV-02"},
                ]
            }
        ]

        for cat_data in catalog:
            cat = db.query(MenuCategory).filter(MenuCategory.name == cat_data["category"]).first()
            if not cat:
                cat = MenuCategory(
                    name=cat_data["category"],
                    description=cat_data["description"],
                    restaurant_id=restaurant.id
                )
                db.add(cat)
                db.commit()
                db.refresh(cat)
                print(f"Created category: {cat.name}")

            for item_data in cat_data["items"]:
                existing_item = db.query(MenuItem).filter(MenuItem.name == item_data["name"]).first()
                if not existing_item:
                    new_item = MenuItem(
                        restaurant_id=restaurant.id,
                        category_id=cat.id,
                        item_code=item_data["code"],
                        name=item_data["name"],
                        description=item_data["description"],
                        price=item_data["price"],
                        quantity=100,
                        is_available=True,
                        is_deleted=False,
                        image_url=None
                    )
                    db.add(new_item)
                    print(f"   + Added item: {item_data['name']} (Rs. {item_data['price']})")
        db.commit()
        print("\nAll sample data successfully seeded into restaurant.db!")
    except Exception as e:
        db.rollback()
        print(f"Seeding error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_sample_data()
