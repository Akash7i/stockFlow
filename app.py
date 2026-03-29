from flask import Flask, render_template, request, jsonify, send_file
import mysql.connector
from datetime import datetime
import io
import csv

app = Flask(__name__)

# -------------------------
# MySQL CONNECTION
# -------------------------
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="stock"
    )

# -------------------------
# AUTO CREATE TABLES
# -------------------------
def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            price DECIMAL(10,2) DEFAULT 0,
            qty INT DEFAULT 0,
            reorder_level INT DEFAULT 10,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INT AUTO_INCREMENT PRIMARY KEY,
            total_amount DECIMAL(10,2) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bill_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            bill_id INT NOT NULL,
            product_name VARCHAR(255),
            qty INT,
            price DECIMAL(10,2),
            FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

# -------------------------
# SERVE MAIN PAGE
# -------------------------
@app.route("/")
def index():
    return render_template("stock7flow_iphone.html")

# -------------------------
# PRODUCTS API
# -------------------------
@app.route("/api/products", methods=["GET"])
def get_products():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products ORDER BY name")
    products = cur.fetchall()
    cur.close()
    conn.close()
    # Convert Decimal to float for JSON
    for p in products:
        p["price"] = float(p["price"])
    return jsonify(products)


@app.route("/api/products", methods=["POST"])
def add_product():
    data = request.json
    name = (data.get("name") or "").strip()
    price = float(data.get("price") or 0)
    qty = int(data.get("qty") or 0)
    reorder = int(data.get("reorder") or 10)

    if not name:
        return jsonify({"error": "Name required"}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO products (name, price, qty, reorder_level) VALUES (%s,%s,%s,%s)",
            (name, price, qty, reorder)
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.close()
        conn.close()
        return jsonify({"id": new_id, "name": name, "price": price, "qty": qty, "reorder": reorder}), 201
    except mysql.connector.IntegrityError:
        cur.close()
        conn.close()
        return jsonify({"error": "Product already exists"}), 409


@app.route("/api/products/<int:pid>", methods=["PUT"])
def update_product(pid):
    data = request.json
    name = (data.get("name") or "").strip()
    price = float(data.get("price") or 0)
    qty = int(data.get("qty") or 0)
    reorder = int(data.get("reorder") or 10)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE products SET name=%s, price=%s, qty=%s, reorder_level=%s WHERE id=%s",
        (name, price, qty, reorder, pid)
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/products/<int:pid>", methods=["DELETE"])
def delete_product(pid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id=%s", (pid,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})

# -------------------------
# BILLING API
# -------------------------
@app.route("/api/bills", methods=["POST"])
def create_bill():
    """
    Expects JSON:
    {
      "items": [
        {"product_id": 1, "product_name": "Tomatoes", "qty": 2, "price": 25.0},
        ...
      ],
      "total": 50.0
    }
    """
    data = request.json
    items = data.get("items", [])
    total = float(data.get("total", 0))

    if not items:
        return jsonify({"error": "No items"}), 400

    conn = get_db()
    cur = conn.cursor()

    # Check stock availability & deduct
    for item in items:
        pid = item.get("product_id")
        sold_qty = int(item.get("qty", 0))

        cur.execute("SELECT qty FROM products WHERE id=%s", (pid,))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({"error": f"Product ID {pid} not found"}), 404

        available = row[0]
        if sold_qty > available:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({"error": f"Not enough stock for '{item.get('product_name')}'"}), 400

        cur.execute(
            "UPDATE products SET qty = qty - %s WHERE id=%s",
            (sold_qty, pid)
        )

    # Insert bill
    cur.execute(
        "INSERT INTO bills (total_amount, created_at) VALUES (%s, %s)",
        (total, datetime.now())
    )
    bill_id = cur.lastrowid

    # Insert bill items
    for item in items:
        cur.execute(
            "INSERT INTO bill_items (bill_id, product_name, qty, price) VALUES (%s,%s,%s,%s)",
            (bill_id, item.get("product_name"), int(item.get("qty")), float(item.get("price")))
        )

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True, "bill_id": bill_id}), 201


@app.route("/api/bills", methods=["GET"])
def get_bills():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM bills ORDER BY created_at DESC LIMIT 50")
    bills = cur.fetchall()

    result = []
    for b in bills:
        cur.execute("SELECT * FROM bill_items WHERE bill_id=%s", (b["id"],))
        items = cur.fetchall()
        for i in items:
            i["price"] = float(i["price"])
        result.append({
            "id": b["id"],
            "total": float(b["total_amount"]),
            "date": b["created_at"].strftime("%d-%m-%Y %I:%M %p"),
            "items": items
        })

    cur.close()
    conn.close()
    return jsonify(result)

# -------------------------
# EXPORT CSV
# -------------------------
@app.route("/api/export")
def export_csv():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, price, qty, reorder_level FROM products ORDER BY name")
    products = cur.fetchall()
    cur.close()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Name", "Price", "Quantity", "Reorder Level"])
    for p in products:
        writer.writerow([p["id"], p["name"], float(p["price"]), p["qty"], p["reorder_level"]])

    buf.seek(0)
    return send_file(
        io.BytesIO(buf.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name="stock7flow_export.csv"
    )

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    init_db()
    print("✅ Database tables initialized")
    print("🚀 Stock7Flow running at http://localhost:5000")
    app.run(debug=True)