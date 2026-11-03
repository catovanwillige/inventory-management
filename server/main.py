from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
    unit_cost: float
    category: str

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

# --- Restocking ---

# Supplier lead time in days, by category. Categories not listed use the default.
LEAD_TIME_DAYS = {
    'Circuit Boards': 14,
    'Sensors': 10,
    'Actuators': 12,
    'Controllers': 14,
    'Power Supplies': 7,
    'Mechanical Components': 9,
}
DEFAULT_LEAD_TIME_DAYS = 10

# Submitted restocking orders. Held in memory only, so a server restart clears them.
restock_orders: list = []

class RestockRecommendation(BaseModel):
    sku: str
    name: str
    category: str
    trend: str
    current_demand: int
    forecasted_demand: int
    stock_on_hand: int
    suggested_quantity: int
    unit_cost: float
    line_cost: float
    lead_time_days: int
    already_ordered: bool
    urgency_rank: int

class RestockOrderItemRequest(BaseModel):
    sku: str
    quantity: int

class CreateRestockOrderRequest(BaseModel):
    budget: float
    items: List[RestockOrderItemRequest]

class RestockLine(BaseModel):
    sku: str
    name: str
    category: str
    quantity: int
    unit_cost: float
    line_total: float
    lead_time_days: int

class RestockOrder(BaseModel):
    id: str
    items: List[RestockLine]
    total_cost: float
    budget: float
    status: str
    submitted_date: str
    lead_time_days: int
    expected_delivery: str

def get_lead_time(category: str) -> int:
    return LEAD_TIME_DAYS.get(category, DEFAULT_LEAD_TIME_DAYS)

def ordered_skus() -> set:
    return {line["sku"] for order in restock_orders for line in order["items"]}

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/restock/recommendations", response_model=List[RestockRecommendation])
def get_restock_recommendations():
    """Get restocking suggestions for every demand forecast, ranked by urgency"""
    stock_by_sku = {item["sku"]: item["quantity_on_hand"] for item in inventory_items}
    already = ordered_skus()

    rows = []
    for f in demand_forecasts:
        # Most forecast SKUs have no inventory record. For those, treat current
        # demand as the stock on hand, so the suggestion covers forecast growth.
        stock = stock_by_sku.get(f["item_sku"], f["current_demand"])
        suggested = max(f["forecasted_demand"] - stock, 0)
        rows.append({
            "sku": f["item_sku"],
            "name": f["item_name"],
            "category": f["category"],
            "trend": f["trend"],
            "current_demand": f["current_demand"],
            "forecasted_demand": f["forecasted_demand"],
            "stock_on_hand": stock,
            "suggested_quantity": suggested,
            "unit_cost": f["unit_cost"],
            "line_cost": round(suggested * f["unit_cost"], 2),
            "lead_time_days": get_lead_time(f["category"]),
            "already_ordered": f["item_sku"] in already,
        })

    # Urgency: increasing trends first, then the largest shortfall.
    rows.sort(key=lambda r: (r["trend"] != "increasing", -r["suggested_quantity"]))
    for rank, row in enumerate(rows, start=1):
        row["urgency_rank"] = rank
    return rows

@app.get("/api/restock-orders", response_model=List[RestockOrder])
def get_restock_orders():
    """Get submitted restocking orders, newest first"""
    return list(reversed(restock_orders))

@app.post("/api/restock-orders", response_model=RestockOrder, status_code=201)
def create_restock_order(request: CreateRestockOrderRequest):
    """Submit a restocking order. Prices are taken from the server, not the request."""
    if not request.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    forecasts_by_sku = {f["item_sku"]: f for f in demand_forecasts}
    already = ordered_skus()
    seen = set()
    lines = []
    for item in request.items:
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Quantity for {item.sku} must be greater than 0")
        forecast = forecasts_by_sku.get(item.sku)
        if not forecast:
            raise HTTPException(status_code=404, detail=f"Item {item.sku} not found")
        if item.sku in already or item.sku in seen:
            raise HTTPException(status_code=409, detail=f"Item {item.sku} is already on a submitted order")
        seen.add(item.sku)
        lines.append({
            "sku": item.sku,
            "name": forecast["item_name"],
            "category": forecast["category"],
            "quantity": item.quantity,
            "unit_cost": forecast["unit_cost"],
            "line_total": round(item.quantity * forecast["unit_cost"], 2),
            "lead_time_days": get_lead_time(forecast["category"]),
        })

    total = round(sum(line["line_total"] for line in lines), 2)
    if total > request.budget:
        raise HTTPException(status_code=400, detail=f"Order total {total} exceeds budget {request.budget}")

    # Items ship together, so the order arrives when its slowest item does.
    lead_time = max(line["lead_time_days"] for line in lines)
    submitted = datetime.now().replace(microsecond=0)
    order = {
        "id": f"RST-{len(restock_orders) + 1:04d}",
        "items": lines,
        "total_cost": total,
        "budget": request.budget,
        "status": "Submitted",
        "submitted_date": submitted.isoformat(),
        "lead_time_days": lead_time,
        "expected_delivery": (submitted + timedelta(days=lead_time)).date().isoformat(),
    }
    restock_orders.append(order)
    return order

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

# --- Tasks ---
# Backs the header Tasks modal (client/src/App.vue). Held in memory only.

class Task(BaseModel):
    # String IDs ("TASK-0001") so they never collide with the numeric IDs
    # of the mock tasks that useAuth.js merges into the same list.
    id: str
    title: str
    priority: str
    dueDate: str
    status: str

class CreateTaskRequest(BaseModel):
    title: str
    priority: str = "medium"
    dueDate: str

tasks: list = []
_task_counter = 0

def _find_task(task_id: str) -> dict:
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task

@app.get("/api/tasks", response_model=List[Task])
def get_tasks():
    """List tasks, newest first."""
    return list(reversed(tasks))

@app.post("/api/tasks", response_model=Task, status_code=201)
def create_task(request: CreateTaskRequest):
    """Create a pending task."""
    global _task_counter
    if not request.title.strip():
        raise HTTPException(status_code=400, detail="Title must not be empty")
    if request.priority not in ("high", "medium", "low"):
        raise HTTPException(status_code=400, detail="Priority must be high, medium or low")
    # Monotonic counter rather than len(tasks), so IDs aren't reused after a delete.
    _task_counter += 1
    task = {
        "id": f"TASK-{_task_counter:04d}",
        "title": request.title.strip(),
        "priority": request.priority,
        "dueDate": request.dueDate,
        "status": "pending",
    }
    tasks.append(task)
    return task

@app.patch("/api/tasks/{task_id}", response_model=Task)
def toggle_task(task_id: str):
    """Toggle a task between pending and completed."""
    task = _find_task(task_id)
    task["status"] = "completed" if task["status"] == "pending" else "pending"
    return task

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    """Delete a task."""
    tasks.remove(_find_task(task_id))
    return {"deleted": task_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
