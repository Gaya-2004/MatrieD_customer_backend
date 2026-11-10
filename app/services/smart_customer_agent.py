"""
smart_customer_agent.py

Enhanced NLU & Conversational Ordering Agent for MaitreD.
Resolves customer intents, fuzzy item matches, cart mutations,
screen navigations, and multilingual replies (English, Tamil, Tanglish).
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from ..models.menu import MenuItem, MenuCategory

logger = logging.getLogger(__name__)

# Common food stopwords
STOPWORDS = {
    "please", "want", "order", "give", "me", "add", "some", "the",
    "food", "dish", "item", "items", "kudunga", "venum", "to", "my",
    "cart", "plate", "plates", "piece", "pieces", "one", "two", "three",
    "four", "five", "six", "seven", "eight", "nine", "ten", "rendu",
    "oru", "irandu", "moonu", "naalu", "in", "a", "an", "also", "and"
}


def detect_language(text: str) -> str:
    """Detects if text contains Tamil script or common Tanglish phonetics."""
    if re.search(r'[\u0B80-\u0BFF]', text):
        return "ta"
    tanglish_words = [
        "venum", "kudunga", "iruka", "illai", "evlo", "sapadu", "sapad",
        "kaatu", "kaatunga", "podu", "seri", "aama", "illa", "rendu",
        "oru", "moonu", "naalu", "nandri", "romba", "nalla", "veedu"
    ]
    words = text.lower().split()
    if any(w in tanglish_words for w in words):
        return "tanglish"
    return "en"


STEM_MAP = {
    'dosai': 'dosa', 'dosas': 'dosa',
    'vadai': 'vada', 'vadas': 'vada',
    'biriyani': 'biryani', 'briyani': 'biryani', 'biriyanis': 'biryani',
    'parotha': 'parotta', 'parotta': 'parotta', 'parottas': 'parotta', 'parothas': 'parotta',
    'idlis': 'idly', 'idli': 'idly', 'idlies': 'idly',
    'poori': 'puri', 'poorir': 'puri',
    'pongal': 'pongal',
    'chappathi': 'chapati', 'chappathi': 'chapati', 'chapathi': 'chapati',
}

def stem_word(w: str) -> str:
    cleaned = re.sub(r'[^a-z]', '', w.lower())
    return STEM_MAP.get(cleaned, cleaned)


def _clean_token(t: str) -> str:
    return stem_word(t)


def find_matching_menu_items(db: Session, query: str, restaurant_id: Optional[int] = None) -> List[MenuItem]:
    """
    Finds matching menu items from real backend DB using strict keyword, stem, and canonical-word matching.
    Prioritizes plain/canonical items (e.g. 'Idly (2)') over modified items ('Mini Kaima Idly').
    """
    q = db.query(MenuItem).filter(MenuItem.is_deleted == False)
    if restaurant_id:
        items = q.filter(MenuItem.restaurant_id == restaurant_id).all()
        if not items:
            items = q.all()
    else:
        items = q.all()

    if not items:
        return []

    clean_q = query.lower().strip()
    clean_q = re.sub(r'\b(plate|plates|piece|pieces|nos|cup|cups|portion|portions)\b', '', clean_q).strip()

    # Filter out stopwords and numbers to get the core target dish name
    tokens = [stem_word(t) for t in clean_q.split() if stem_word(t) not in STOPWORDS and not t.isdigit() and len(stem_word(t)) > 1]
    
    if not tokens:
        tokens = [stem_word(t) for t in clean_q.split() if len(stem_word(t)) > 1]

    scored = []
    core_dish_name = " ".join(tokens)

    for item in items:
        name_lower = item.name.lower()
        # Stem all words in item name
        clean_item_words = [stem_word(w) for w in name_lower.split() if stem_word(w)]
        
        score = 0

        # 1. Exact pure name match (e.g. user said "idly" and item is "Idly (2)")
        if clean_item_words == tokens:
            score += 1000
        else:
            # Check how many user tokens are matched
            matched_count = sum(1 for t in tokens if any(t == w or (len(t) > 3 and t in w) for w in clean_item_words))
            
            if tokens and matched_count == len(tokens):
                # Matched ALL user query tokens! Massive bonus!
                score += 500 + (matched_count * 150) - (len(clean_item_words) * 15)
                if clean_item_words and tokens and clean_item_words[0] == tokens[0]:
                    score += 50  # starts with target token
            elif matched_count > 0:
                score += matched_count * 40

        # Exact substring bonus
        if core_dish_name and core_dish_name in name_lower:
            score += 80

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored]


def extract_quantity(text: str) -> int:
    """Extracts quantity number from natural language in English, Tamil, and Tanglish."""
    # Digits
    digit_m = re.search(r'\b(\d+)\b', text)
    if digit_m:
        val = int(digit_m.group(1))
        if 1 <= val <= 50:
            return val

    # Words mapping
    word_map = {
        "one": 1, "single": 1, "oru": 1, "onnu": 1,
        "two": 2, "double": 2, "rendu": 2, "irandu": 2,
        "three": 3, "triple": 3, "moonu": 3, "moondru": 3,
        "four": 4, "naalu": 4, "naangu": 4,
        "five": 5, "anju": 5, "aindhu": 5,
        "six": 6, "aaru": 6,
        "seven": 7, "yezhu": 7,
        "eight": 8, "ettu": 8,
        "nine": 9, "ombodhu": 9,
        "ten": 10, "pathu": 10
    }
    for word, qty in word_map.items():
        if re.search(rf'\b{word}\b', text.lower()):
            return qty

    return 1


def process_mobile_voice_turn(
    user_text: str,
    db: Session,
    restaurant_id: Optional[int] = None,
    customer_phone: Optional[str] = None,
    customer_name: Optional[str] = None,
    current_screen: Optional[str] = None,
    cart: Optional[List[Dict[str, Any]]] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Core conversational reasoning function.
    Returns: {
        "assistant_text": str,
        "ui_actions": list,
        "data": dict,
        "requires_confirmation": bool,
        "transcribed_user_text": str
    }
    """
    raw_text = (user_text or "").strip()
    clean_lower = raw_text.lower()
    lang = detect_language(clean_lower)
    cart_items = cart or []

    # Check last message in conversation for confirmations
    last_agent_text = ""
    if chat_history:
        for msg in reversed(chat_history):
            if msg.get("role") in ("agent", "assistant"):
                last_agent_text = msg.get("text", "").lower()
                break

    was_asking_clear_cart = "remove all items from your cart" in last_agent_text or "நீக்க விரும்புகிறீர்களா" in last_agent_text
    was_asking_place_order = "would you like to place this order" in last_agent_text or "பதிவு செய்யலாமா" in last_agent_text

    is_affirmative = bool(re.search(r'\b(yes|yeah|yup|sure|proceed|confirm|ok|okay|aama|aamam|seri|confirm pannu)\b', clean_lower))
    is_negative = bool(re.search(r'\b(no|nope|cancel|dont|don\'t|stop|illa|illai|vendaam|vendam)\b', clean_lower))

    # -------------------------------------------------------------
    # 1. CONFIRMATION RESPONSES
    # -------------------------------------------------------------
    if was_asking_clear_cart:
        if is_affirmative:
            reply = "உங்கள் கார்ட் அழிக்கப்பட்டது." if lang in ("ta", "tanglish") else "I have cleared your cart."
            return {
                "assistant_text": reply,
                "ui_actions": [{"action": "clear_cart"}],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }
        elif is_negative:
            reply = "கார்ட் அழிக்கப்படவில்லை." if lang in ("ta", "tanglish") else "Okay, I kept your cart items safe."
            return {
                "assistant_text": reply,
                "ui_actions": [],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }

    if was_asking_place_order:
        if is_affirmative:
            reply = "உங்கள் ஆர்டர் உறுதி செய்யப்படுகிறது! தயவுசெய்து கட்டண முறையை தேர்ந்தெடுக்கவும்." if lang in ("ta", "tanglish") else "Placing your order now! Please select your payment method."
            return {
                "assistant_text": reply,
                "ui_actions": [
                    {"action": "navigate", "route": "/(checkout)/payment"},
                    {"action": "place_order"}
                ],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }
        elif is_negative:
            reply = "ஆர்டர் ரத்து செய்யப்பட்டது. உங்களுக்கு வேறு என்ன வேண்டும்?" if lang in ("ta", "tanglish") else "Order not placed. You can continue browsing or modify your cart."
            return {
                "assistant_text": reply,
                "ui_actions": [],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }

    # -------------------------------------------------------------
    # 2. GREETING & CONVERSATION START
    # -------------------------------------------------------------
    if re.search(r'\b(hi|hello|hey|vanakkam|வணக்கம்|namaste|good morning|good evening|good afternoon)\b', clean_lower) or clean_lower in ("start", "help", "order food", "i want to order food", "sapadu venum"):
        greet_name = f", {customer_name}" if customer_name else ""
        if lang in ("ta", "tanglish"):
            reply = f"வணக்கம்{greet_name}! MaitreD-க்கு வரவேற்கிறோம். நான் உங்கள் உணவு ஆர்டர் உதவியாளர். இன்று என்ன சுவையான உணவு சாப்பிட விரும்புகிறீர்கள்?"
        else:
            reply = f"Welcome{greet_name}! Thank you for visiting MaitreD. I'm your food ordering assistant. Would you like to explore our menu or search for a particular dish?"
        return {
            "assistant_text": reply,
            "ui_actions": [],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    # -------------------------------------------------------------
    # 3. NAVIGATION COMMANDS
    # -------------------------------------------------------------
    if re.search(r'\b(open home|go home|home page|home screen|veedu|mukappu)\b', clean_lower):
        reply = "முகப்புப் பக்கத்திற்கு செல்கிறேன்." if lang in ("ta", "tanglish") else "Navigating to the home screen."
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/(main)/home"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    if re.search(r'\b(show me the menu|open menu|show menu|view menu|unavupattiyal|menu)\b', clean_lower):
        reply = "எங்கள் உணவக மெனு இதோ! உங்களுக்கு என்ன வேண்டும்?" if lang in ("ta", "tanglish") else "Here is our restaurant menu. What would you like to explore?"
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/menu"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    if re.search(r'\b(show vegetarian|vegetarian items|veg only|veg items|saiva unavu)\b', clean_lower):
        reply = "சைவ உணவுகள் இதோ!" if lang in ("ta", "tanglish") else "Here are our delicious vegetarian dishes!"
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/menu", "payload": {"params": {"search": "veg"}}}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    if re.search(r'\b(show non-veg|non-vegetarian items|non veg|asaiva unavu)\b', clean_lower):
        reply = "அசைவ உணவுகள் இதோ!" if lang in ("ta", "tanglish") else "Here are our popular non-vegetarian selections!"
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/menu", "payload": {"params": {"search": "non-veg"}}}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    if re.search(r'\b(show biryani|biryani items|search biryani)\b', clean_lower):
        reply = "சுவையான பிரியாணி வகைகள் இதோ!" if lang in ("ta", "tanglish") else "Showing our aromatic biryani specials!"
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/menu", "payload": {"params": {"search": "biryani"}}}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    if (
        re.search(r'^(go to (my )?cart|open (the |my )?cart|view (the |my )?cart|show (the |my )?cart|my cart|cart)$', clean_lower)
        or (
            re.search(r'\b(go to cart|open cart|view cart|show cart|my cart)\b', clean_lower)
            and not re.search(r'\b(add|put|order|remove|delete|insert|idly|dosa|biryani|rice|coffee|tea|vada|vadai)\b', clean_lower)
        )
    ):
        reply = "உங்கள் கார்ட் திரைக்கு செல்கிறேன்." if lang in ("ta", "tanglish") else "Opening your cart."
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/(checkout)/checkout"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    if re.search(r'\b(open my orders|order history|my orders|previous orders)\b', clean_lower):
        reply = "உங்கள் ஆர்டர் வரலாறு திரைக்கு செல்கிறேன்." if lang in ("ta", "tanglish") else "Opening your order history."
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/(order)/orders"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    if re.search(r'\b(track my order|track order|live tracking|order status)\b', clean_lower):
        reply = "உங்கள் ஆர்டரை கண்காணிக்கும் பக்கத்திற்கு செல்கிறேன்." if lang in ("ta", "tanglish") else "Opening order tracking."
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/(order)/order-details"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    if re.search(r'\b(go back|back|pin sellu)\b', clean_lower):
        reply = "முந்தைய பக்கத்திற்கு செல்கிறேன்." if lang in ("ta", "tanglish") else "Going back to the previous screen."
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "BACK"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    if re.search(r'\b(close chatbot|close assistant|minimize chatbot|bye|exit)\b', clean_lower):
        reply = "நன்றி! விடைபெறுகிறேன்." if lang in ("ta", "tanglish") else "Closing assistant. Enjoy your meal!"
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "hide_agent"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    # -------------------------------------------------------------
    # 4. OFFERS & COUPONS
    # -------------------------------------------------------------
    if re.search(r'\b(apply offer|apply coupon|save10|discount|any offers|offers)\b', clean_lower):
        code = "SAVE10"
        m_code = re.search(r'\b(save10|welcome50|festive20)\b', clean_lower)
        if m_code:
            code = m_code.group(1).upper()
        reply = f"கூப்பன் '{code}' வெற்றிகரமாக பயன்படுத்தப்பட்டது! 10% தள்ளுபடி வழங்கப்பட்டுள்ளது." if lang in ("ta", "tanglish") else f"Coupon '{code}' applied successfully! 10% discount added to your bill."
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "apply_coupon", "payload": {"coupon_code": code}}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    # -------------------------------------------------------------
    # 5. ORDER TYPE (Dine-in / Takeaway / Delivery)
    # -------------------------------------------------------------
    if re.search(r'\b(takeaway|take away|parcel|pack)\b', clean_lower):
        reply = "ஆர்டர் வகை 'Take Away' என மாற்றப்பட்டது." if lang in ("ta", "tanglish") else "Order type set to Take Away."
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "set_order_type", "order_type": "Take Away"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }
    if re.search(r'\b(dine-in|dine in|table|eating here)\b', clean_lower):
        reply = "ஆர்டர் வகை 'Dine In' என மாற்றப்பட்டது." if lang in ("ta", "tanglish") else "Order type set to Dine In."
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "set_order_type", "order_type": "Dine In"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }
    if re.search(r'\b(delivery|home delivery|door delivery)\b', clean_lower):
        reply = "ஆர்டர் வகை 'Delivery' என மாற்றப்பட்டது." if lang in ("ta", "tanglish") else "Order type set to Delivery."
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "set_order_type", "order_type": "Delivery"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    # -------------------------------------------------------------
    # 6. CLEAR CART
    # -------------------------------------------------------------
    if re.search(r'\b(clear my cart|clear cart|empty cart|delete all)\b', clean_lower):
        reply = "உங்கள் கார்ட்டில் உள்ள அனைத்து உணவுகளையும் நீக்க விரும்புகிறீர்களா? உறுதிப்படுத்த 'ஆம்' அல்லது 'இல்லை' என்று கூறவும்." if lang in ("ta", "tanglish") else "Are you sure you want to remove all items from your cart? Please say 'Yes' to confirm or 'No' to cancel."
        return {
            "assistant_text": reply,
            "ui_actions": [],
            "data": {},
            "requires_confirmation": True,
            "transcribed_user_text": raw_text
        }

    # -------------------------------------------------------------
    # 7. CART TOTAL / BILL SUMMARY (Food price only, NO TAX)
    # -------------------------------------------------------------
    if re.search(r'\b(what is my total|what\'s my total|how much is my bill|total amount|bill summary|calculate total|total|subtotal|bill|bill amount|what is the bill)\b', clean_lower):
        if not cart_items:
            reply = "உங்கள் கார்ட் தற்போது காலியாக உள்ளது." if lang in ("ta", "tanglish") else "Your cart is currently empty. Please add items to view your total."
            return {
                "assistant_text": reply,
                "ui_actions": [],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }
        total = round(sum(float(i.get("price", 0)) * int(i.get("quantity", 1)) for i in cart_items), 2)
        if lang in ("ta", "tanglish"):
            reply = f"உணவுத் தொகை மற்றும் நீங்கள் செலுத்த வேண்டிய மொத்த தொகை ₹{total}."
        else:
            reply = f"Your food total is ₹{total}. Total payable is ₹{total} (no taxes added)."
        return {
            "assistant_text": reply,
            "ui_actions": [],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    # -------------------------------------------------------------
    # 8. CHECKOUT & BILLING
    # -------------------------------------------------------------
    if re.search(r'\b(proceed to checkout|checkout|place order|order now|bill please|place my order)\b', clean_lower):
        if not cart_items:
            reply = "கார்ட்டில் உணவுகள் எதுவும் இல்லை. முதலில் உணவை சேர்க்கவும்." if lang in ("ta", "tanglish") else "Your cart is empty. Please add items before proceeding to checkout."
            return {
                "assistant_text": reply,
                "ui_actions": [{"action": "navigate", "route": "/menu"}],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }

        total = round(sum(float(i.get("price", 0)) * int(i.get("quantity", 1)) for i in cart_items), 2)

        items_breakdown = ", ".join([f"{i.get('name')} ({i.get('quantity')} x ₹{i.get('price')})" for i in cart_items])
        if lang in ("ta", "tanglish"):
            reply = f"உங்கள் ஆர்டர் விவரங்கள்: {items_breakdown}. செலுத்த வேண்டிய மொத்த தொகை ₹{total}. இந்த ஆர்டரை பதிவு செய்யலாமா?"
        else:
            reply = f"Your order summary: {items_breakdown}. Total payable is ₹{total}. Would you like to place this order?"
        
        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/(checkout)/checkout"}],
            "data": {},
            "requires_confirmation": True,
            "transcribed_user_text": raw_text
        }

    # -------------------------------------------------------------
    # 9. PAYMENT
    # -------------------------------------------------------------
    if re.search(r'\b(pay online|pay using upi|pay with upi|pay by cash|cash on delivery|payment options)\b', clean_lower):
        if "cash" in clean_lower:
            reply = "ரொக்கக் கட்டணம் (Cash) தேர்ந்தெடுக்கப்பட்டது. கட்டணப் பக்கத்திற்கு செல்கிறேன்." if lang in ("ta", "tanglish") else "Cash payment option selected. Taking you to the payment screen."
        elif "upi" in clean_lower:
            reply = "UPI கட்டண முறைக்கு வழிநடத்துகிறேன். பாதுகாப்பாக பணம் செலுத்தவும்." if lang in ("ta", "tanglish") else "Navigating to UPI payment. Please complete authorization in the secure gateway."
        else:
            reply = "ஆன்லைன் கட்டண முறைக்கு வழிநடத்துகிறேன்." if lang in ("ta", "tanglish") else "Navigating to online payment."

        return {
            "assistant_text": reply,
            "ui_actions": [{"action": "navigate", "route": "/(checkout)/payment"}],
            "data": {},
            "requires_confirmation": False,
            "transcribed_user_text": raw_text
        }

    # -------------------------------------------------------------
    # 10. REMOVE FROM CART
    # -------------------------------------------------------------
    if re.search(r'\b(remove|delete|cancel item|neekku)\b', clean_lower):
        matching_items = find_matching_menu_items(db, clean_lower, restaurant_id)
        if matching_items:
            target_item = matching_items[0]
            reply = f"{target_item.name} கார்ட்டிலிருந்து நீக்கப்பட்டது." if lang in ("ta", "tanglish") else f"Removed {target_item.name} from your cart."
            return {
                "assistant_text": reply,
                "ui_actions": [{"action": "remove_from_cart", "menu_item_id": target_item.id, "payload": {"item_id": target_item.id, "name": target_item.name}}],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }
        else:
            for ci in cart_items:
                c_name = ci.get("name", "").lower()
                if c_name in clean_lower or any(word in c_name for word in clean_lower.split() if len(word) > 3):
                    reply = f"{ci.get('name')} கார்ட்டிலிருந்து நீக்கப்பட்டது." if lang in ("ta", "tanglish") else f"Removed {ci.get('name')} from your cart."
                    return {
                        "assistant_text": reply,
                        "ui_actions": [{"action": "remove_from_cart", "menu_item_id": ci.get("id"), "payload": {"item_id": ci.get("id"), "name": ci.get("name")}}],
                        "data": {},
                        "requires_confirmation": False,
                        "transcribed_user_text": raw_text
                    }
            reply = "கார்ட்டில் எந்த உணவு நீக்கப்பட வேண்டும் என்று குறிப்பிடவும்." if lang in ("ta", "tanglish") else "Please specify which item you would like to remove from the cart."
            return {
                "assistant_text": reply,
                "ui_actions": [],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }

    # -------------------------------------------------------------
    # 11. QUANTITY MODIFICATIONS
    # -------------------------------------------------------------
    if re.search(r'\b(add one more|innum onnu|increase|reduce|decrease|make it|change quantity)\b', clean_lower):
        qty = extract_quantity(clean_lower)
        matching_items = find_matching_menu_items(db, clean_lower, restaurant_id)
        target_id = None
        target_name = None

        if matching_items:
            target_id = matching_items[0].id
            target_name = matching_items[0].name
        elif cart_items:
            last_item = cart_items[-1]
            target_id = last_item.get("id")
            target_name = last_item.get("name")

        if target_id and target_name:
            if "make it" in clean_lower or "set to" in clean_lower or re.search(r'\bmake it \d+\b', clean_lower):
                reply = f"{target_name} எண்ணிக்கை {qty} ஆக மாற்றப்பட்டது." if lang in ("ta", "tanglish") else f"Updated {target_name} quantity to {qty}."
                return {
                    "assistant_text": reply,
                    "ui_actions": [{"action": "set_cart_quantity", "menu_item_id": target_id, "quantity": qty, "payload": {"item_id": target_id}}],
                    "data": {},
                    "requires_confirmation": False,
                    "transcribed_user_text": raw_text
                }
            elif "reduce" in clean_lower or "decrease" in clean_lower:
                reply = f"{target_name} எண்ணிக்கை குறைக்கப்பட்டது." if lang in ("ta", "tanglish") else f"Decreased quantity for {target_name}."
                return {
                    "assistant_text": reply,
                    "ui_actions": [{"action": "decrement_cart_item", "menu_item_id": target_id, "payload": {"item_id": target_id}}],
                    "data": {},
                    "requires_confirmation": False,
                    "transcribed_user_text": raw_text
                }
            else:
                reply = f"{target_name} மேலும் ஒன்று சேர்க்கப்பட்டது." if lang in ("ta", "tanglish") else f"Added one more {target_name} to your cart."
                return {
                    "assistant_text": reply,
                    "ui_actions": [{"action": "increment_cart_item", "menu_item_id": target_id, "payload": {"item_id": target_id}}],
                    "data": {},
                    "requires_confirmation": False,
                    "transcribed_user_text": raw_text
                }

    # -------------------------------------------------------------
    # 12. MENU SEARCH & ITEM QUERY / ADD TO CART
    # -------------------------------------------------------------
    matched_items = find_matching_menu_items(db, clean_lower, restaurant_id)

    is_asking_info = bool(re.search(r'\b(do you have|available|iruka|price|evlo|how much|cost|rate)\b', clean_lower))
    is_asking_to_add = bool(re.search(r'\b(add|want|give|venum|kudunga|order|plate|plates)\b', clean_lower)) or extract_quantity(clean_lower) > 1

    if matched_items:
        first_item = matched_items[0]

        # Check if top item is an exact canonical match (e.g. user said "idly" -> "Idly (2)")
        top_name_words = [re.sub(r'[^a-z]', '', w) for w in first_item.name.lower().split() if re.sub(r'[^a-z]', '', w)]
        user_dish_tokens = [re.sub(r'[^a-z]', '', t) for t in clean_lower.split() if re.sub(r'[^a-z]', '', t) not in STOPWORDS and len(re.sub(r'[^a-z]', '', t)) > 1]
        is_exact_canonical = bool(top_name_words and user_dish_tokens and top_name_words == user_dish_tokens)

        # Ambiguity check: only prompt when NO exact canonical match exists
        if not is_exact_canonical and len(matched_items) > 1 and len(clean_lower.split()) <= 2 and not is_asking_to_add:
            candidates = [f"{item.name} (₹{item.price})" for item in matched_items[:3]]
            cand_str = ", ".join(candidates)
            if lang in ("ta", "tanglish"):
                reply = f"எங்களிடம் பல வகைகள் உள்ளன: {cand_str}. உங்களுக்கு எது வேண்டும்?"
            else:
                reply = f"We have several options: {cand_str}. Which one would you prefer?"
            return {
                "assistant_text": reply,
                "ui_actions": [{"action": "navigate", "route": "/menu", "payload": {"params": {"search": clean_lower}}}],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }

        if is_asking_info and not is_asking_to_add:
            status_text = "கிடைக்கிறது" if first_item.is_available else "தற்போது இல்லை"
            eng_status = "available" if first_item.is_available else "currently out of stock"
            if lang in ("ta", "tanglish"):
                reply = f"ஆம்! {first_item.name} விலை ₹{first_item.price}, மற்றும் {status_text}. உங்கள் கார்ட்டில் சேர்க்க விரும்புகிறீர்களா?"
            else:
                reply = f"Yes! {first_item.name} is {eng_status} at ₹{first_item.price}. Would you like to add it to your cart?"
            return {
                "assistant_text": reply,
                "ui_actions": [],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }

        # Otherwise, Add to Cart!
        if first_item.is_available:
            qty = extract_quantity(clean_lower)
            total_item_price = float(first_item.price) * qty

            # Detect customization notes
            customization = None
            if "spicy" in clean_lower or "extra spicy" in clean_lower:
                customization = "Spicy"
            elif "less spicy" in clean_lower or "mild" in clean_lower:
                customization = "Less spicy"
            elif "no onion" in clean_lower or "no onions" in clean_lower:
                customization = "No onions"
            elif "extra cheese" in clean_lower:
                customization = "Extra cheese"

            custom_desc = f" ({customization})" if customization else ""

            if lang in ("ta", "tanglish"):
                reply = f"{qty} {first_item.name}{custom_desc} கார்ட்டில் சேர்க்கப்பட்டது (₹{total_item_price}). வேறு என்ன வேண்டும்?"
            else:
                reply = f"Added {qty} {first_item.name}{custom_desc} to your cart for ₹{total_item_price}. Would you like anything else?"

            item_payload = {
                "id": first_item.id,
                "name": first_item.name,
                "price": float(first_item.price),
                "image": getattr(first_item, "image_url", "") or "",
                "category": getattr(first_item, "category_id", "General"),
                "desc": first_item.description or "",
                "note": customization or ""
            }

            return {
                "assistant_text": reply,
                "ui_actions": [
                    {
                        "action": "add_to_cart",
                        "menu_item_id": first_item.id,
                        "quantity": qty,
                        "payload": {"item": item_payload, "quantity": qty}
                    }
                ],
                "data": {},
                "requires_confirmation": False,
                "transcribed_user_text": raw_text
            }

    # Fallback response
    if lang in ("ta", "tanglish"):
        reply = "மன்னிக்கவும், நீங்கள் குறிப்பிட்ட உணவு கிடைக்கவில்லை. எங்கள் மெனுவை பார்க்க 'Show menu' என்று கூறவும்."
    else:
        reply = "I'm sorry, I couldn't find that dish. You can say 'Show menu' to browse all available options."

    return {
        "assistant_text": reply,
        "ui_actions": [],
        "data": {},
        "requires_confirmation": False,
        "transcribed_user_text": raw_text
    }
