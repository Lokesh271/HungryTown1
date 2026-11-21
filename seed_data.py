"""
Simulated restaurant data for Hungry Town.

We don't build a real food-ordering/delivery system for the hackathon —
that's out of scope. Instead we simulate the operational data (drivers,
routes, traffic, timing) that a real system would have, so Detective Mode
has something real to investigate.
"""

ORDERS = {
    "#1042": {
        "driver": "Driver 04",
        "driver_orders_assigned": 4,
        "traffic": "heavy",
        "expected_delivery_min": 25,
        "actual_delivery_min": 58,
        "route": "Route B",
    },
    "#1043": {
        "driver": "Driver 02",
        "driver_orders_assigned": 1,
        "traffic": "normal",
        "expected_delivery_min": 20,
        "actual_delivery_min": 18,
        "route": "Route A",
    },
    "#1044": {
        "driver": "Driver 07",
        "driver_orders_assigned": 2,
        "traffic": "normal",
        "expected_delivery_min": 22,
        "actual_delivery_min": 24,
        "route": "Route C",
    },
    "#1045": {
        "driver": "Driver 04",
        "driver_orders_assigned": 3,
        "traffic": "heavy",
        "expected_delivery_min": 20,
        "actual_delivery_min": 47,
        "route": "Route B",
    },
    "#1046": {
        "driver": "Driver 09",
        "driver_orders_assigned": 1,
        "traffic": "normal",
        "expected_delivery_min": 18,
        "actual_delivery_min": 16,
        "route": "Route D",
    },
}


def seed_reviews():
    """A handful of demo reviews so the dashboard isn't empty on first launch."""
    return [
        {"order_id": "#1042", "rating": 2,
         "text": "Food was good but delivery was very late, took almost an hour."},
        {"order_id": "#1043", "rating": 5,
         "text": "Amazing experience! Food arrived fast and hot."},
        {"order_id": "#1044", "rating": 3,
         "text": "Food arrived cold, but the delivery time was fine."},
        {"order_id": "#1045", "rating": 1,
         "text": "Never again. Order never arrived on time and driver was rude."},
        {"order_id": "#1046", "rating": 5,
         "text": "Great service, friendly delivery person, food was fresh."},
    ]
