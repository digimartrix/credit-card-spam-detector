"""
Real-time transaction generator module.

Simulates continuous incoming credit card transactions with realistic data
including Indian/foreign locations, popular merchants, random amounts, and
timestamps. Transactions are generated automatically to mimic a live banking
feed that the fraud detection engine processes in near real-time.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Realistic simulation data pools
# ---------------------------------------------------------------------------

INDIAN_CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad",
    "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow",
    "Kochi", "Chandigarh", "Coimbatore", "Surat", "Indore",
]

FOREIGN_CITIES = [
    "New York", "London", "Dubai", "Singapore", "Tokyo",
    "Paris", "Sydney", "Hong Kong", "Toronto", "Berlin",
]

MERCHANTS = [
    "Amazon", "Flipkart", "Swiggy", "Zomato", "BigBasket",
    "Myntra", "BookMyShow", "MakeMyTrip", "PhonePe Merchant",
    "Croma", "Reliance Digital", "Shell Fuel", "HP Petrol",
    "Apollo Pharmacy", "Uber", "Ola", "Netflix", "Spotify",
    "Google Play", "Apple Store",
]

# Maps merchants to the fraud-model's merchant_type categories
MERCHANT_CATEGORY_MAP = {
    "Amazon": "Online Retail",
    "Flipkart": "Online Retail",
    "Swiggy": "Dining",
    "Zomato": "Dining",
    "BigBasket": "Grocery",
    "Myntra": "Online Retail",
    "BookMyShow": "Entertainment",
    "MakeMyTrip": "Travel",
    "PhonePe Merchant": "Digital Goods",
    "Croma": "Electronics",
    "Reliance Digital": "Electronics",
    "Shell Fuel": "Fuel",
    "HP Petrol": "Fuel",
    "Apollo Pharmacy": "Healthcare",
    "Uber": "Travel",
    "Ola": "Travel",
    "Netflix": "Entertainment",
    "Spotify": "Digital Goods",
    "Google Play": "Digital Goods",
    "Apple Store": "Electronics",
}

FAKE_NAMES = [
    "Aarav Mehta", "Priya Nair", "Daniel Brooks", "Sophia Carter",
    "Riya Shah", "Michael Torres", "Ananya Gupta", "Vikram Singh",
    "Neha Reddy", "Amit Kumar", "Divya Sharma", "Rajesh Patel",
    "Kavitha Iyer", "Sanjay Verma", "Meera Krishnan", "Arjun Das",
]

# ---------------------------------------------------------------------------
# Transaction scenarios with weighted probabilities
# ---------------------------------------------------------------------------

SCENARIOS = {
    "normal_small": {
        "weight": 0.40,
        "amount_range": (50.0, 500.0),
        "hour_range": (8, 21),
        "location_type": "domestic",
        "merchant_pool": ["Amazon", "Flipkart", "Swiggy", "Zomato", "BigBasket",
                          "Myntra", "Shell Fuel", "HP Petrol", "Apollo Pharmacy"],
    },
    "normal_medium": {
        "weight": 0.25,
        "amount_range": (500.0, 3000.0),
        "hour_range": (9, 20),
        "location_type": "domestic",
        "merchant_pool": ["Amazon", "Flipkart", "Croma", "BookMyShow",
                          "Reliance Digital", "MakeMyTrip"],
    },
    "suspicious_foreign": {
        "weight": 0.15,
        "amount_range": (1000.0, 8000.0),
        "hour_range": (0, 23),
        "location_type": "foreign",
        "merchant_pool": ["Amazon", "MakeMyTrip", "Uber", "Apple Store", "Netflix"],
    },
    "high_risk": {
        "weight": 0.10,
        "amount_range": (5000.0, 50000.0),
        "hour_range": (0, 5),
        "location_type": "foreign",
        "merchant_pool": ["PhonePe Merchant", "Google Play", "Apple Store",
                          "Croma", "Reliance Digital"],
    },
    "micro_transaction": {
        "weight": 0.10,
        "amount_range": (10.0, 100.0),
        "hour_range": (6, 22),
        "location_type": "domestic",
        "merchant_pool": ["Spotify", "Netflix", "Google Play", "Uber", "Ola"],
    },
}


# ---------------------------------------------------------------------------
# Thread-safe transaction buffer
# ---------------------------------------------------------------------------

class TransactionBuffer:
    """Thread-safe circular buffer that stores the most recent transactions."""

    def __init__(self, maxlen: int = 100):
        self._buffer: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._counter = 0

    def push(self, transaction: dict[str, Any]) -> None:
        with self._lock:
            self._counter += 1
            transaction["id"] = self._counter
            self._buffer.appendleft(transaction)

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._buffer[0]) if self._buffer else None

    def recent(self, count: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in list(self._buffer)[:count]]

    def count(self) -> int:
        with self._lock:
            return self._counter


# Singleton buffer instance shared across the application
_transaction_buffer = TransactionBuffer(maxlen=200)


def get_transaction_buffer() -> TransactionBuffer:
    """Return the global transaction buffer."""
    return _transaction_buffer


# ---------------------------------------------------------------------------
# Transaction generation logic
# ---------------------------------------------------------------------------

def _pick_scenario() -> dict[str, Any]:
    """Select a transaction scenario using weighted random selection."""
    names = list(SCENARIOS.keys())
    weights = [SCENARIOS[name]["weight"] for name in names]
    chosen = random.choices(names, weights=weights, k=1)[0]
    return SCENARIOS[chosen]


def generate_live_transaction() -> dict[str, Any]:
    """
    Generate a single realistic transaction.

    Returns a dictionary containing all fields needed for both display
    (merchant name, city) and ML prediction (merchant_type, location).
    """
    rng = np.random.default_rng()
    scenario = _pick_scenario()

    # Amount with slight randomness
    amount = round(float(rng.uniform(*scenario["amount_range"])), 2)

    # Time: use current time or simulate within the scenario's hour range
    use_current_time = random.random() < 0.6
    if use_current_time:
        now = datetime.now()
        tx_time = now.strftime("%H:%M")
        tx_timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    else:
        hour = int(rng.integers(scenario["hour_range"][0], scenario["hour_range"][1] + 1))
        minute = int(rng.integers(0, 60))
        tx_time = f"{hour:02d}:{minute:02d}"
        tx_timestamp = datetime.now().strftime(f"%Y-%m-%d {tx_time}:%S")

    # Location
    if scenario["location_type"] == "domestic":
        city = random.choice(INDIAN_CITIES)
        location = "Domestic"
    else:
        city = random.choice(FOREIGN_CITIES)
        location = "International"

    # Merchant
    merchant_name = random.choice(scenario["merchant_pool"])
    merchant_type = MERCHANT_CATEGORY_MAP.get(merchant_name, "Online Retail")

    # Card details
    holder_name = random.choice(FAKE_NAMES)
    card_digits = "".join(str(random.randint(0, 9)) for _ in range(16))
    card_masked = f"**** **** **** {card_digits[-4:]}"

    return {
        "card_number": card_digits,
        "card_holder_name": holder_name,
        "card_masked": card_masked,
        "transaction_amount": amount,
        "transaction_time": tx_time,
        "timestamp": tx_timestamp,
        "location": location,
        "city": city,
        "merchant_name": merchant_name,
        "merchant_type": merchant_type,
    }


# ---------------------------------------------------------------------------
# Background generator thread
# ---------------------------------------------------------------------------

_generator_thread: threading.Thread | None = None
_generator_running = False


def _generator_loop(interval_min: float = 3.0, interval_max: float = 5.0) -> None:
    """Background loop that pushes new transactions into the buffer."""
    global _generator_running
    buffer = get_transaction_buffer()

    while _generator_running:
        transaction = generate_live_transaction()
        buffer.push(transaction)
        sleep_time = random.uniform(interval_min, interval_max)
        time.sleep(sleep_time)


def start_generator(interval_min: float = 3.0, interval_max: float = 5.0) -> None:
    """Start the background transaction generator (idempotent)."""
    global _generator_thread, _generator_running

    if _generator_running and _generator_thread and _generator_thread.is_alive():
        return

    _generator_running = True
    _generator_thread = threading.Thread(
        target=_generator_loop,
        args=(interval_min, interval_max),
        daemon=True,
        name="transaction-generator",
    )
    _generator_thread.start()


def stop_generator() -> None:
    """Signal the background generator to stop."""
    global _generator_running
    _generator_running = False
