# pyrefly: ignore [missing-import]
import logging
import os
import base64
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File

logger = logging.getLogger(__name__)
# pyrefly: ignore [missing-import]
from pydantic import BaseModel
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, date, timedelta
from collections import defaultdict
from ..db import SessionLocal
from ..models.delivery import DeliveryPartner, DeliveryAssignment, RiderDocument, RiderBankDetail, RiderSession
from ..models.order import Order, OrderItem
from ..models.restaurant import Restaurant
from ..utils.auth import create_rider_token, verify_password, hash_password
from ..utils.dependencies import get_current_rider

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class RiderLoginPayload(BaseModel):
    phone: str
    password: str


class RiderRegisterPayload(BaseModel):
    name: str
    phone: str
    password: str


class SetPasswordPayload(BaseModel):
    phone: str
    password: str
    name: Optional[str] = None


@router.post("/api/v1/rider/auth/register")
def rider_register(payload: RiderRegisterPayload, db: Session = Depends(get_db)):
    name = payload.name.strip()
    raw_phone = payload.phone.strip()
    pwd = payload.password.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not raw_phone:
        raise HTTPException(status_code=400, detail="Phone number is required")
    if not pwd:
        raise HTTPException(status_code=400, detail="Password is required")
    if len(pwd) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")

    clean_digits = "".join([c for c in raw_phone if c.isdigit()])
    if len(clean_digits) == 12 and clean_digits.startswith("91"):
        clean_phone = clean_digits[2:]
    elif len(clean_digits) == 11 and clean_digits.startswith("0"):
        clean_phone = clean_digits[1:]
    else:
        clean_phone = clean_digits

    if len(clean_phone) != 10 or clean_phone[0] not in ("6", "7", "8", "9"):
        raise HTTPException(
            status_code=400,
            detail="Invalid phone number."
        )

    # Check if rider already exists
    existing = db.query(DeliveryPartner).filter(
        (DeliveryPartner.phone == raw_phone) |
        (DeliveryPartner.phone == clean_phone) |
        (DeliveryPartner.phone == f"+91{clean_phone}") |
        (DeliveryPartner.phone.ilike(f"%{clean_phone}%"))
    ).first()

    if not existing:
        # Create new delivery partner account
        rider = DeliveryPartner(
            name=name,
            phone=clean_phone,
            password_hash=hash_password(pwd),
            is_active=True,
            is_online=True,
            is_available=True,
            rating=5.0,
            total_rides=0,
            total_ratings=0
        )
        db.add(rider)
        db.commit()
        db.refresh(rider)
    else:
        if existing.password_hash:
            raise HTTPException(
                status_code=400,
                detail="Account already registered with this phone number. Please sign in with your password."
            )

        if not existing.is_active:
            raise HTTPException(
                status_code=401,
                detail="Account is disabled. Please contact administrator."
            )

        # Authorized rider completing registration / setting initial password
        existing.name = name
        existing.password_hash = hash_password(pwd)
        existing.is_active = True
        existing.is_online = True
        existing.is_available = True
        db.commit()
        rider = existing

    token_info = create_rider_token(rider.id)
    new_session = RiderSession(
        rider_id=rider.id,
        jti=token_info["jti"],
        expires_at=token_info["expires_at"],
        is_revoked=False
    )
    db.add(new_session)
    db.commit()

    return {
        "access_token": token_info["access_token"],
        "token": token_info["token"],
        "token_type": "bearer",
        "expires_in": token_info["expires_in"],
        "rider": {
            "id": rider.id,
            "name": rider.name,
            "phone": rider.phone,
            "is_active": rider.is_active,
            "is_online": rider.is_online,
            "is_available": rider.is_available,
            "rating": round(rider.rating or 0.0, 1),
            "total_rides": rider.total_rides or 0,
        }
    }


@router.post("/api/v1/rider/auth/set-password")
def set_rider_password(payload: SetPasswordPayload, db: Session = Depends(get_db)):
    raw_phone = payload.phone.strip()
    clean_digits = "".join([c for c in raw_phone if c.isdigit()])
    if len(clean_digits) == 12 and clean_digits.startswith("91"):
        clean_phone = clean_digits[2:]
    elif len(clean_digits) == 11 and clean_digits.startswith("0"):
        clean_phone = clean_digits[1:]
    else:
        clean_phone = clean_digits

    if len(clean_phone) != 10 or clean_phone[0] not in ("6", "7", "8", "9"):
        raise HTTPException(
            status_code=400,
            detail="Invalid phone number. Must be a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9."
        )

    rider = db.query(DeliveryPartner).filter(
        (DeliveryPartner.phone == raw_phone) |
        (DeliveryPartner.phone == clean_phone) |
        (DeliveryPartner.phone == f"+91{clean_phone}") |
        (DeliveryPartner.phone.ilike(f"%{clean_phone}%"))
    ).first()

    if not rider:
        raise HTTPException(status_code=404, detail="Rider not registered with this phone number.")

    if not rider.is_active:
        raise HTTPException(status_code=401, detail="Account is disabled. Please contact administrator.")

    pwd = payload.password.strip()
    if len(pwd) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")

    if payload.name and payload.name.strip():
        rider.name = payload.name.strip()

    rider.password_hash = hash_password(pwd)
    db.commit()
    return {"message": "Password updated successfully. You can now log in."}



@router.post("/api/v1/rider/auth/login")
def rider_login(payload: RiderLoginPayload, db: Session = Depends(get_db)):
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required")

    raw_phone = payload.phone.strip()
    clean_digits = "".join([c for c in raw_phone if c.isdigit()])
    if len(clean_digits) == 12 and clean_digits.startswith("91"):
        clean_phone = clean_digits[2:]
    elif len(clean_digits) == 11 and clean_digits.startswith("0"):
        clean_phone = clean_digits[1:]
    else:
        clean_phone = clean_digits

    # Strict Indian 10-digit phone number check
    if len(clean_phone) != 10 or clean_phone[0] not in ("6", "7", "8", "9"):
        raise HTTPException(
            status_code=400,
            detail="Invalid phone number. Must be a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9."
        )

    rider = db.query(DeliveryPartner).filter(
        (DeliveryPartner.phone == raw_phone) |
        (DeliveryPartner.phone == clean_phone) |
        (DeliveryPartner.phone == f"+91{clean_phone}") |
        (DeliveryPartner.phone.ilike(f"%{clean_phone}%"))
    ).first()

    if not rider:
        # Generic error message to prevent account enumeration
        raise HTTPException(status_code=401, detail="Invalid phone number or password")

    if not rider.is_active:
        raise HTTPException(status_code=401, detail="Account is disabled. Please contact administrator.")

    if not rider.password_hash:
        raise HTTPException(status_code=401, detail="Password has not been set for this account. Please set up your password.")

    if not verify_password(payload.password, rider.password_hash):
        raise HTTPException(status_code=401, detail="Invalid phone number or password")

    active_assignment = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.rider_id == rider.id,
        DeliveryAssignment.status.notin_(["DELIVERED", "REJECTED", "CANCELLED", "FAILED", "ASSIGNED"])
    ).first()

    rider.is_online = True
    if active_assignment:
        rider.is_available = False
    else:
        rider.is_available = True

    token_info = create_rider_token(rider.id)

    # Record active session in rider_sessions table
    new_session = RiderSession(
        rider_id=rider.id,
        jti=token_info["jti"],
        expires_at=token_info["expires_at"],
        is_revoked=False
    )
    db.add(new_session)
    db.commit()

    return {
        "access_token": token_info["access_token"],
        "token": token_info["token"],
        "token_type": "bearer",
        "expires_in": token_info["expires_in"],
        "rider": {
            "id": rider.id,
            "name": rider.name,
            "phone": rider.phone,
            "is_active": rider.is_active,
            "is_online": rider.is_online,
            "is_available": rider.is_available,
            "rating": round(rider.rating or 0.0, 1),
            "total_rides": rider.total_rides or 0,
        }
    }


@router.post("/api/v1/rider/auth/logout")
def rider_logout(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    # Server-side token revocation: revoke the active session
    jti = getattr(current_rider, "_token_jti", None)
    if jti:
        session_rec = db.query(RiderSession).filter(RiderSession.jti == jti).first()
        if session_rec:
            session_rec.is_revoked = True

    # Set rider offline upon logout
    current_rider.is_online = False
    current_rider.is_available = False
    db.commit()

    return {"message": "Rider logged out successfully"}


def format_assignment_data(assignment: DeliveryAssignment, order: Order, restaurant: Optional[Restaurant], db: Session):
    import json
    
    # Query items for the order
    items = []
    items_count = 0
    if order:
        order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        items_count = len(order_items)
        for oi in order_items:
            item_name = oi.menu_item.name if oi.menu_item else f"Item #{oi.menu_item_id}"
            item_price = oi.price if oi.price is not None else (oi.menu_item.price if oi.menu_item else 0.0)
            items.append({
                "id": oi.id,
                "menu_item_id": oi.menu_item_id,
                "name": item_name,
                "quantity": oi.quantity or 1,
                "price": float(item_price or 0.0),
                "total_price": round(float(item_price or 0.0) * (oi.quantity or 1), 2)
            })

    # Parse delivery_address snapshot
    raw_addr = (order.delivery_address_snapshot if order else {}) or {}
    if isinstance(raw_addr, str):
        try:
            raw_addr = json.loads(raw_addr)
        except Exception:
            raw_addr = {"address_line": raw_addr}

    customer_address_str = raw_addr.get("address_line") or raw_addr.get("full_address") or raw_addr.get("address") or (getattr(order, "delivery_address", "") if order else "") or ""
    customer_name = raw_addr.get("contact_name") or raw_addr.get("name") or getattr(order, "customer_name", None) or "Customer"
    customer_phone = raw_addr.get("contact_phone") or raw_addr.get("phone") or getattr(order, "customer_phone", None) or ""
    
    cust_lat = float(raw_addr.get("latitude")) if raw_addr.get("latitude") is not None else (float(raw_addr.get("lat")) if raw_addr.get("lat") is not None else None)
    cust_lng = float(raw_addr.get("longitude")) if raw_addr.get("longitude") is not None else (float(raw_addr.get("lng")) if raw_addr.get("lng") is not None else None)

    formatted_delivery_addr = {
        "address_line": customer_address_str,
        "full_address": customer_address_str,
        "landmark": raw_addr.get("landmark") or "",
        "instructions": (order.delivery_instructions if order else None) or raw_addr.get("instructions") or "",
        "contact_name": customer_name,
        "contact_phone": customer_phone,
        "latitude": cust_lat,
        "longitude": cust_lng,
    }

    rest_lat = float(restaurant.latitude) if restaurant and getattr(restaurant, "latitude", None) is not None else None
    rest_lng = float(restaurant.longitude) if restaurant and getattr(restaurant, "longitude", None) is not None else None

    formatted_restaurant = {
        "id": restaurant.id if restaurant else None,
        "name": restaurant.name if restaurant else "Restaurant",
        "address": restaurant.address if restaurant else None,
        # Return None if phone is genuinely unavailable — never fabricate
        "phone": getattr(restaurant, "phone", None) or None,
        "latitude": rest_lat,
        "longitude": rest_lng
    }

    total_amount = float(order.total_amount) if order and order.total_amount else 0.0
    # Use only real earnings recorded on the assignment; never fabricate
    estimated_earnings = float(getattr(assignment, "earnings", None) or 0.0) or None
    tip_amount = float(getattr(order, "tip_amount", None) or 0.0) or None

    # Real payment values only — no fallback fabrication
    payment_method = (order.payment_method if order and hasattr(order, "payment_method") and order.payment_method else None)
    payment_status = (order.payment_status if order and hasattr(order, "payment_status") and order.payment_status else None)

    return {
        "assignment_id": assignment.id,
        "order_id": assignment.order_id,
        "order_type": order.order_type if order and getattr(order, "order_type", None) else "DELIVERY",
        "display_order_id": f"ORD-{str(assignment.order_id).zfill(6)}",
        "status": assignment.status,
        "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at else None,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "restaurant_name": formatted_restaurant["name"],
        "restaurant_address": formatted_restaurant["address"],
        "restaurant": formatted_restaurant,
        "customer_address": customer_address_str,
        "delivery_address": formatted_delivery_addr,
        "items": items,
        "items_count": len(items) if items else items_count,
        "total_amount": total_amount,
        "tip_amount": tip_amount,
        "estimated_earnings": estimated_earnings,
        "payment_method": payment_method,
        "payment_status": payment_status,
    }


@router.get("/api/v1/rider/delivery-requests")
def get_delivery_requests(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider_id = current_rider.id
    assignments = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.rider_id == rider_id,
        DeliveryAssignment.status == "ASSIGNED"
    ).all()

    requests = []
    for assignment in assignments:
        order = db.query(Order).filter(
            Order.id == assignment.order_id,
            Order.order_type.ilike("DELIVERY")
        ).first()
        if order:
            restaurant = db.query(Restaurant).filter(Restaurant.id == order.restaurant_id).first()
            requests.append(format_assignment_data(assignment, order, restaurant, db))
    return {"delivery_requests": requests}


@router.get("/api/v1/rider/deliveries/current")
def get_current_delivery(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider_id = current_rider.id
    assignments = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.rider_id == rider_id,
        DeliveryAssignment.status.notin_(["DELIVERED", "REJECTED", "CANCELLED", "FAILED", "ASSIGNED"])
    ).all()

    if not assignments:
        return {"current_assignment": None, "current_trip": []}

    trip = []
    for assignment in assignments:
        order = db.query(Order).filter(
            Order.id == assignment.order_id,
            Order.order_type.ilike("DELIVERY")
        ).first()
        if order:
            restaurant = db.query(Restaurant).filter(Restaurant.id == order.restaurant_id).first()
            trip.append(format_assignment_data(assignment, order, restaurant, db))

    if not trip:
        return {"current_assignment": None, "current_trip": []}

    return {
        "current_assignment": trip[0], # Backward compatibility
        "current_trip": trip
    }


@router.get("/api/v1/rider/available-orders")
def get_available_orders(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    """
    Returns the delivery order explicitly assigned to this rider by the dispatcher.
    """
    rider_assignments = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.status == "ASSIGNED",
        DeliveryAssignment.rider_id == current_rider.id
    ).all()

    # If no pending offer and rider is available, online, and active, attempt to dispatch any waiting unassigned orders
    if not rider_assignments and current_rider.is_online and current_rider.is_active and current_rider.is_available:
        try:
            unassigned_order_ids = [
                row[0] for row in db.query(Order.id).join(
                    DeliveryAssignment, DeliveryAssignment.order_id == Order.id
                ).filter(
                    Order.order_type.ilike("DELIVERY"),
                    Order.status.notin_(["CANCELLED", "COMPLETED", "SERVED"]),
                    DeliveryAssignment.status == "UNASSIGNED",
                    DeliveryAssignment.rider_id.is_(None)
                ).order_by(Order.created_at.asc()).limit(3).all()
            ]
            if unassigned_order_ids:
                from ..services.dispatch import dispatch_order
                for u_id in unassigned_order_ids:
                    dispatched = dispatch_order(db, u_id)
                    if dispatched and dispatched.rider_id == current_rider.id and dispatched.status == "ASSIGNED":
                        rider_assignments.append(dispatched)
                        break
        except Exception as _disp_err:
            logger.error(f"Error in on-demand dispatch during poll: {_disp_err}")

    result = []
    for assignment in rider_assignments:
        order = db.query(Order).filter(
            Order.id == assignment.order_id,
            Order.order_type.ilike("DELIVERY"),
            Order.status.notin_(["CANCELLED", "COMPLETED"])
        ).first()
        if order:
            restaurant = db.query(Restaurant).filter(Restaurant.id == order.restaurant_id).first()
            result.append(format_assignment_data(assignment, order, restaurant, db))

    return {"delivery_requests": result}


@router.post("/api/v1/rider/available-orders/{order_id}/accept")
def accept_available_order(order_id: int, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    """
    Allows a rider to accept a dispatched order offered to them.
    Transitions status to ACCEPTED.
    """
    from ..models.delivery import DeliveryStatusHistory
    from ..services.delivery_status import update_delivery_status

    rider_id = current_rider.id

    # Check batch limit
    active_count = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.rider_id == rider_id,
        DeliveryAssignment.status.notin_(["DELIVERED", "REJECTED", "CANCELLED", "FAILED", "UNASSIGNED", "ASSIGNED"])
    ).count()
    
    MAX_ACTIVE_ORDERS_PER_RIDER = 2
    if active_count >= MAX_ACTIVE_ORDERS_PER_RIDER:
        raise HTTPException(status_code=400, detail="You have reached the maximum active orders limit.")

    # Find the ASSIGNED assignment for this order and rider
    assignment = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.order_id == order_id,
        DeliveryAssignment.status == "ASSIGNED",
        DeliveryAssignment.rider_id == rider_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="This order is no longer available (already accepted or reassigned).")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Accept the assignment using the standard status transition
    update_delivery_status(db, assignment.id, "ACCEPTED", "Rider accepted the dispatched order")
    
    # We must refresh since update_delivery_status modifies it
    db.refresh(assignment)

    restaurant = db.query(Restaurant).filter(Restaurant.id == order.restaurant_id).first()
    return {
        "success": True,
        "assignment": format_assignment_data(assignment, order, restaurant, db)
    }


@router.get("/api/v1/rider/stats")
def get_rider_stats(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider_id = current_rider.id
    total_rides = current_rider.total_rides or 0
    rating = round(current_rider.rating or 0.0, 1)

    today_start = datetime.combine(date.today(), datetime.min.time())
    week_start = today_start - timedelta(days=today_start.weekday())

    today_assignments = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.rider_id == rider_id,
        DeliveryAssignment.status == "DELIVERED",
        DeliveryAssignment.delivered_at >= today_start
    ).all()

    week_assignments = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.rider_id == rider_id,
        DeliveryAssignment.status == "DELIVERED",
        DeliveryAssignment.delivered_at >= week_start
    ).all()

    today_earnings = 0.0
    for a in today_assignments:
        order = getattr(a, "order", None)
        if order:
            today_earnings += float(getattr(order, "delivery_fee", 0.0) or 0.0)
            today_earnings += float(getattr(order, "tip_amount", 0.0) or 0.0)

    week_earnings = 0.0
    for a in week_assignments:
        order = getattr(a, "order", None)
        if order:
            week_earnings += float(getattr(order, "delivery_fee", 0.0) or 0.0)
            week_earnings += float(getattr(order, "tip_amount", 0.0) or 0.0)

    total_delivered = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.rider_id == rider_id,
        DeliveryAssignment.status == "DELIVERED"
    ).count()

    take_home = float(getattr(current_rider, "take_home_earnings", 0.0) or (total_delivered * 45.0))
    esi_pf = float(getattr(current_rider, "esi_pf_amount", 0.0) or (total_delivered * 12.0))
    platform_fee = float(getattr(current_rider, "platform_fee_amount", 0.0) or (total_delivered * 3.0))

    return {
        "today_earnings": round(len(today_assignments) * 45.0, 2),
        "deliveries_today": len(today_assignments),
        "total_rides": total_rides or total_delivered,
        "rating": rating,
        "this_week_earnings": round(len(week_assignments) * 45.0, 2),
        "take_home_charge": round(take_home, 2),
        "esi_pf_charge": round(esi_pf, 2),
        "platform_fee_charge": round(platform_fee, 2),
    }


@router.get("/api/v1/rider/deliveries/history")
def get_delivery_history(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider_id = current_rider.id
    assignments = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.rider_id == rider_id
    ).order_by(DeliveryAssignment.assigned_at.desc()).all()

    history = []
    import json as _json
    for assignment in assignments:
        order = db.query(Order).filter(Order.id == assignment.order_id).first()
        restaurant = db.query(Restaurant).filter(Restaurant.id == order.restaurant_id).first() if order else None

        earnings = None
        if order:
            earnings = float(getattr(order, "delivery_fee", 0.0) or 0.0) + float(getattr(order, "tip_amount", 0.0) or 0.0)
            if earnings == 0.0:
                earnings = None

        # Parse customer name from delivery address snapshot
        customer_name = None
        customer_address = None
        if order and order.delivery_address_snapshot:
            raw = order.delivery_address_snapshot
            if isinstance(raw, str):
                try:
                    raw = _json.loads(raw)
                except Exception:
                    raw = {}
            if isinstance(raw, dict):
                customer_name = raw.get("contact_name") or raw.get("name") or getattr(order, "customer_name", None)
                customer_address = raw.get("address_line") or raw.get("full_address") or raw.get("address")

        items_count = db.query(OrderItem).filter(OrderItem.order_id == assignment.order_id).count() if order else 0

        history.append({
            "id": assignment.id,
            "order_id": assignment.order_id,
            "display_order_id": f"ORD-{str(assignment.order_id).zfill(6)}",
            "status": assignment.status,
            "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at else None,
            "delivered_at": assignment.delivered_at.isoformat() if assignment.delivered_at else None,
            "restaurant_name": restaurant.name if restaurant else None,
            "customer_name": customer_name,
            "customer_address": customer_address,
            "items_count": items_count,
            "earnings": earnings,
            "total_amount": float(order.total_amount) if order and order.total_amount else None,
        })

    return history


@router.get("/api/v1/rider/earnings/history")
def get_earnings_history(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider_id = current_rider.id
    assignments = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.rider_id == rider_id,
        DeliveryAssignment.status == "DELIVERED"
    ).order_by(DeliveryAssignment.delivered_at.desc()).all()

    earnings_by_date = defaultdict(lambda: {"total_earnings": 0.0, "deliveries_count": 0})

    for assignment in assignments:
        date_str = (assignment.delivered_at or assignment.assigned_at or datetime.utcnow()).strftime("%Y-%m-%d")
        order = getattr(assignment, "order", None)
        earnings = 0.0
        if order:
            earnings = float(getattr(order, "delivery_fee", 0.0) or 0.0) + float(getattr(order, "tip_amount", 0.0) or 0.0)
        
        earnings_by_date[date_str]["total_earnings"] += earnings
        earnings_by_date[date_str]["deliveries_count"] += 1

    earnings_list = []
    for date_key, data in sorted(earnings_by_date.items(), reverse=True):
        earnings_list.append({
            "date": date_key,
            "total_earnings": round(data["total_earnings"], 2),
            "deliveries_count": data["deliveries_count"]
        })

    return earnings_list


@router.get("/api/v1/rider/deliveries/{assignment_id}")
def get_rider_delivery_assignment(assignment_id: int, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider_id = current_rider.id
    assignment = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.id == assignment_id,
        DeliveryAssignment.rider_id == rider_id
    ).first()

    if not assignment:
        raise HTTPException(status_code=404, detail="Delivery assignment not found")

    order = db.query(Order).filter(Order.id == assignment.order_id).first()
    restaurant = db.query(Restaurant).filter(Restaurant.id == order.restaurant_id).first() if order else None

    return format_assignment_data(assignment, order, restaurant, db)


# ── Delivery Partner profile endpoints (called by frontend) ──────────────────

@router.get("/api/v1/delivery-partners/{rider_id}")
def get_delivery_partner(rider_id: int, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    if current_rider.id != rider_id:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot access another rider's profile")
    rider = db.query(DeliveryPartner).filter(DeliveryPartner.id == rider_id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    return {
        "id": rider.id,
        "name": rider.name,
        "phone": rider.phone,
        "email": rider.email,
        "vehicle_type": rider.vehicle_type,
        "vehicle_number": rider.vehicle_number,
        "rating": round(rider.rating or 0.0, 1),
        "total_rides": rider.total_rides or 0,
        "is_online": rider.is_online,
        "is_available": rider.is_available,
        "profile_image": rider.profile_image,
    }


class OnlineStatusPayload(BaseModel):
    is_online: bool


class AvailabilityPayload(BaseModel):
    is_available: bool


@router.patch("/api/v1/delivery-partners/{rider_id}/online-status")
def patch_online_status(rider_id: int, payload: OnlineStatusPayload, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    if current_rider.id != rider_id:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot modify another rider's status")
    rider = db.query(DeliveryPartner).filter(DeliveryPartner.id == rider_id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    rider.is_online = payload.is_online
    if not payload.is_online:
        rider.is_available = False
    db.commit()
    return {"id": rider.id, "is_online": rider.is_online, "is_available": rider.is_available}


@router.patch("/api/v1/delivery-partners/{rider_id}/availability")
def patch_availability(rider_id: int, payload: AvailabilityPayload, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    if current_rider.id != rider_id:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot modify another rider's availability")
    rider = db.query(DeliveryPartner).filter(DeliveryPartner.id == rider_id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    rider.is_available = payload.is_available
    db.commit()
    return {"id": rider.id, "is_online": rider.is_online, "is_available": rider.is_available}


# ── Authenticated Rider Endpoints (/me) ───────────────────────────────────

@router.get("/api/v1/riders/me")
@router.get("/api/v1/rider/me")
def get_rider_me(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider = db.query(DeliveryPartner).filter(DeliveryPartner.id == current_rider.id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    
    # Check vehicle completeness
    has_vehicle = bool(rider.vehicle_type and (rider.vehicle_type.lower() == 'bicycle' or (rider.vehicle_number and len(rider.vehicle_number.strip()) >= 3)))
    
    # Check bank completeness
    bank = db.query(RiderBankDetail).filter(RiderBankDetail.rider_id == rider.id).first()
    has_bank = bool(bank and bank.account_number and bank.ifsc_code)
    
    # Check documents completeness
    docs = db.query(RiderDocument).filter(RiderDocument.rider_id == rider.id, RiderDocument.document_url.isnot(None)).all()
    doc_types = {d.document_type for d in docs if d.document_url}
    has_license = "license" in doc_types
    has_id = bool("aadhaar_front" in doc_types or "pan_card" in doc_types)
    has_docs = has_license and has_id
    
    completed_count = (1 if has_vehicle else 0) + (1 if has_bank else 0) + (1 if has_docs else 0)
    if completed_count == 3:
        completion_percentage = 100
    elif completed_count == 2:
        completion_percentage = 67
    elif completed_count == 1:
        completion_percentage = 33
    else:
        completion_percentage = 0
        
    is_profile_completed = (completion_percentage == 100)
    
    return {
        "id": rider.id,
        "name": rider.name,
        "phone": rider.phone,
        "email": rider.email,
        "profile_image": rider.profile_image,
        "vehicle_type": rider.vehicle_type,
        "vehicle_number": rider.vehicle_number,
        "vehicle_ownership": rider.vehicle_ownership,
        "vehicle_brand": rider.vehicle_brand,
        "vehicle_model": rider.vehicle_model,
        "fuel_type": rider.fuel_type,
        "vehicle_color": rider.vehicle_color,
        "take_home_earnings": round(float(getattr(rider, "take_home_earnings", 0.0) or 0.0), 2),
        "esi_pf_amount": round(float(getattr(rider, "esi_pf_amount", 0.0) or 0.0), 2),
        "platform_fee_amount": round(float(getattr(rider, "platform_fee_amount", 0.0) or 0.0), 2),
        "rating": round(rider.rating or 0.0, 1),
        "total_ratings": rider.total_ratings or 0,
        "total_rides": rider.total_rides or 0,
        "is_online": rider.is_online,
        "is_available": rider.is_available,
        "is_active": rider.is_active,
        "current_latitude": rider.current_latitude,
        "current_longitude": rider.current_longitude,
        "last_location_at": rider.last_location_at,
        "is_profile_completed": is_profile_completed,
        "profile_completion_percentage": completion_percentage,
        "completion_details": {
            "vehicle_info": has_vehicle,
            "bank_details": has_bank,
            "documents": has_docs,
        }
    }

class RiderUpdatePayload(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    profile_image: Optional[str] = None

@router.patch("/api/v1/riders/me")
def update_rider_me(payload: RiderUpdatePayload, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider = db.query(DeliveryPartner).filter(DeliveryPartner.id == current_rider.id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    
    if payload.name is not None:
        rider.name = payload.name
    if payload.email is not None:
        rider.email = payload.email
    if payload.profile_image is not None:
        rider.profile_image = payload.profile_image
        
    db.commit()
    db.refresh(rider)
    return get_rider_me(current_rider, db)


@router.get("/api/v1/riders/me/vehicle")
@router.get("/api/v1/rider/vehicle")
def get_rider_vehicle(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider = db.query(DeliveryPartner).filter(DeliveryPartner.id == current_rider.id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    return {
        "vehicle_type": rider.vehicle_type,
        "vehicle_ownership": rider.vehicle_ownership,
        "vehicle_number": rider.vehicle_number,
        "vehicle_brand": rider.vehicle_brand,
        "vehicle_model": rider.vehicle_model,
        "fuel_type": rider.fuel_type,
        "vehicle_color": rider.vehicle_color,
    }

class VehicleUpdatePayload(BaseModel):
    vehicle_type: Optional[str] = None
    vehicle_ownership: Optional[str] = None
    vehicle_number: Optional[str] = None
    vehicle_brand: Optional[str] = None
    vehicle_model: Optional[str] = None
    fuel_type: Optional[str] = None
    vehicle_color: Optional[str] = None

@router.patch("/api/v1/riders/me/vehicle")
@router.put("/api/v1/riders/me/vehicle")
@router.patch("/api/v1/rider/vehicle")
@router.put("/api/v1/rider/vehicle")
def update_rider_vehicle(payload: VehicleUpdatePayload, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    rider = db.query(DeliveryPartner).filter(DeliveryPartner.id == current_rider.id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    
    if payload.vehicle_type is not None:
        rider.vehicle_type = payload.vehicle_type
    if payload.vehicle_ownership is not None:
        rider.vehicle_ownership = payload.vehicle_ownership
    if payload.vehicle_number is not None:
        rider.vehicle_number = payload.vehicle_number.strip().upper() if payload.vehicle_number else None
    if payload.vehicle_brand is not None:
        rider.vehicle_brand = payload.vehicle_brand
    if payload.vehicle_model is not None:
        rider.vehicle_model = payload.vehicle_model
    if payload.fuel_type is not None:
        rider.fuel_type = payload.fuel_type
    if payload.vehicle_color is not None:
        rider.vehicle_color = payload.vehicle_color
        
    db.commit()
    db.refresh(rider)
    return {
        "vehicle_type": rider.vehicle_type,
        "vehicle_ownership": rider.vehicle_ownership,
        "vehicle_number": rider.vehicle_number,
        "vehicle_brand": rider.vehicle_brand,
        "vehicle_model": rider.vehicle_model,
        "fuel_type": rider.fuel_type,
        "vehicle_color": rider.vehicle_color,
    }

def _process_document_image(rider_id: int, doc_type: str, raw_val: str) -> str:
    """Save base64 encoded document images to persistent static storage and return the URL."""
    if not raw_val or not isinstance(raw_val, str):
        return raw_val
    if raw_val.startswith("http://") or raw_val.startswith("https://") or raw_val.startswith("/static/"):
        return raw_val
        
    data_to_decode = raw_val
    ext = "jpg"
    if "base64," in raw_val:
        header, data_to_decode = raw_val.split("base64,", 1)
        if "png" in header:
            ext = "png"
        elif "webp" in header:
            ext = "webp"
            
    try:
        image_bytes = base64.b64decode(data_to_decode)
        if len(image_bytes) > 20:
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            static_doc_dir = os.path.join(backend_dir, "static", "rider_documents")
            os.makedirs(static_doc_dir, exist_ok=True)
            filename = f"rider_{rider_id}_{doc_type}_{uuid.uuid4().hex[:6]}.{ext}"
            filepath = os.path.join(static_doc_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            return f"/static/rider_documents/{filename}"
    except Exception as e:
        logger.error(f"Error saving base64 document {doc_type}: {e}")
        
    return raw_val

class RiderDocumentPayload(BaseModel):
    aadhaar_front: Optional[str] = None
    aadhaar_back: Optional[str] = None
    pan_card: Optional[str] = None
    license: Optional[str] = None

@router.get("/api/v1/riders/me/documents")
@router.get("/api/v1/rider/documents")
def get_rider_documents(request: Request, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    docs = db.query(RiderDocument).filter(RiderDocument.rider_id == current_rider.id).all()
    result = {
        "aadhaar_front": None,
        "aadhaar_back": None,
        "pan_card": None,
        "license": None,
        "is_verified": False,
        "uploaded_count": 0,
        "is_complete": False
    }
    
    verified_count = 0
    uploaded_count = 0
    base_url = str(request.base_url).rstrip("/")
    
    for doc in docs:
        url = doc.document_url
        if url and url.startswith("/static/"):
            url = f"{base_url}{url}"
            
        if doc.document_type == "aadhaar_front":
            result["aadhaar_front"] = url
        elif doc.document_type == "aadhaar_back":
            result["aadhaar_back"] = url
        elif doc.document_type == "pan_card":
            result["pan_card"] = url
        elif doc.document_type == "license":
            result["license"] = url
            
        if doc.document_url:
            uploaded_count += 1
        if doc.verification_status == "VERIFIED":
            verified_count += 1
            
    has_license = bool(result["license"])
    has_id = bool(result["aadhaar_front"] or result["pan_card"])
    result["uploaded_count"] = uploaded_count
    result["is_complete"] = has_license and has_id
    result["is_verified"] = verified_count >= 2
        
    return result

@router.patch("/api/v1/riders/me/documents")
@router.put("/api/v1/riders/me/documents")
@router.post("/api/v1/riders/me/documents")
@router.patch("/api/v1/rider/documents")
@router.put("/api/v1/rider/documents")
def update_rider_documents(request: Request, payload: RiderDocumentPayload, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    docs = db.query(RiderDocument).filter(RiderDocument.rider_id == current_rider.id).all()
    doc_map = {doc.document_type: doc for doc in docs}
    
    def update_or_create(doc_type, url):
        processed_url = _process_document_image(current_rider.id, doc_type, url)
        if doc_type in doc_map:
            doc_map[doc_type].document_url = processed_url
            doc_map[doc_type].verification_status = "PENDING"
        else:
            new_doc = RiderDocument(
                rider_id=current_rider.id,
                document_type=doc_type,
                document_url=processed_url,
                verification_status="PENDING"
            )
            db.add(new_doc)
            
    if payload.aadhaar_front is not None:
        update_or_create("aadhaar_front", payload.aadhaar_front)
    if payload.aadhaar_back is not None:
        update_or_create("aadhaar_back", payload.aadhaar_back)
    if payload.pan_card is not None:
        update_or_create("pan_card", payload.pan_card)
    if payload.license is not None:
        update_or_create("license", payload.license)
        
    db.commit()
    
    return get_rider_documents(request, current_rider, db)

@router.post("/api/v1/riders/me/documents/{document_type}/upload")
@router.post("/api/v1/rider/documents/{document_type}/upload")
async def upload_rider_document_file(
    document_type: str,
    file: UploadFile = File(...),
    current_rider=Depends(get_current_rider),
    db: Session = Depends(get_db)
):
    if document_type not in ["aadhaar_front", "aadhaar_back", "pan_card", "license"]:
        raise HTTPException(status_code=400, detail="Invalid document type")
        
    ext = (file.filename or "doc.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "pdf"):
        ext = "jpg"
        
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    static_doc_dir = os.path.join(backend_dir, "static", "rider_documents")
    os.makedirs(static_doc_dir, exist_ok=True)
    filename = f"rider_{current_rider.id}_{document_type}_{uuid.uuid4().hex[:6]}.{ext}"
    filepath = os.path.join(static_doc_dir, filename)
    
    with open(filepath, "wb") as buf:
        shutil.copyfileobj(file.file, buf)
        
    url = f"/static/rider_documents/{filename}"
    
    doc = db.query(RiderDocument).filter(
        RiderDocument.rider_id == current_rider.id,
        RiderDocument.document_type == document_type
    ).first()
    
    if doc:
        doc.document_url = url
        doc.verification_status = "PENDING"
    else:
        doc = RiderDocument(
            rider_id=current_rider.id,
            document_type=document_type,
            document_url=url,
            verification_status="PENDING"
        )
        db.add(doc)
        
    db.commit()
    return {"document_type": document_type, "document_url": url, "verification_status": "PENDING"}

class RiderBankDetailPayload(BaseModel):
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    bank_name: Optional[str] = None

@router.get("/api/v1/riders/me/bank-details")
@router.get("/api/v1/rider/bank-details")
def get_rider_bank_details(current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    bank = db.query(RiderBankDetail).filter(RiderBankDetail.rider_id == current_rider.id).first()
    if not bank:
        return {}
    return {
        "account_name": bank.account_name,
        "account_number": bank.account_number,
        "ifsc_code": bank.ifsc_code,
        "bank_name": bank.bank_name
    }

@router.patch("/api/v1/riders/me/bank-details")
@router.put("/api/v1/riders/me/bank-details")
@router.post("/api/v1/riders/me/bank-details")
@router.patch("/api/v1/rider/bank-details")
@router.put("/api/v1/rider/bank-details")
def update_rider_bank_details(payload: RiderBankDetailPayload, current_rider=Depends(get_current_rider), db: Session = Depends(get_db)):
    bank = db.query(RiderBankDetail).filter(RiderBankDetail.rider_id == current_rider.id).first()
    if not bank:
        bank = RiderBankDetail(rider_id=current_rider.id)
        db.add(bank)
        
    if payload.account_name is not None:
        bank.account_name = payload.account_name.strip() if payload.account_name else None
    if payload.account_number is not None:
        bank.account_number = payload.account_number.strip() if payload.account_number else None
    if payload.ifsc_code is not None:
        bank.ifsc_code = payload.ifsc_code.strip().upper() if payload.ifsc_code else None
    if payload.bank_name is not None:
        bank.bank_name = payload.bank_name.strip() if payload.bank_name else None
        
    db.commit()
    db.refresh(bank)
    return {
        "account_name": bank.account_name,
        "account_number": bank.account_number,
        "ifsc_code": bank.ifsc_code,
        "bank_name": bank.bank_name
    }

