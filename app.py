from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
import pandas as pd
import io
from datetime import datetime
import mysql.connector

app = Flask(__name__)
app.secret_key = "change_this_secret_for_prod"

# -------------------------
# MYSQL CONNECTION
# -------------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",   # 🔥 change this
        database="inventory_db"
    )

# -------------------------
# DASHBOARD
# -------------------------
@app.route("/")
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM product ORDER BY name")
    products = cursor.fetchall()

    low_stock = [p for p in products if p["qty"] <= p["reorder_level"]]
    labels = [p["name"] for p in products]
    data_qty = [p["qty"] for p in products]

    cursor.close()
    conn.close()

    return render_template("dashboard.html",
                           products=products,
                           low_stock=low_stock,
                           chart_labels=labels,
                           chart_data=data_qty)

# -------------------------
# PRODUCTS
# -------------------------
@app.route("/products", methods=["GET", "POST"])
def products_page():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        price = float(request.form.get("price") or 0)
        qty = int(request.form.get("qty") or 0)
        reorder = int(request.form.get("reorder_level") or 10)

        if not name:
            flash("Product name is required.", "danger")
            return redirect(url_for("products_page"))

        try:
            cursor.execute(
                "INSERT INTO product (name, price, qty, reorder_level) VALUES (%s,%s,%s,%s)",
                (name, price, qty, reorder)
            )
            conn.commit()
            flash(f"Product '{name}' added.", "success")
        except:
            flash("Product already exists.", "warning")

        return redirect(url_for("products_page"))

    cursor.execute("SELECT * FROM product ORDER BY name")
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("products.html", products=products)

# -------------------------
# EDIT PRODUCT
# -------------------------
@app.route("/product/edit/<int:pid>", methods=["GET", "POST"])
def edit_product(pid):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM product WHERE id = %s", (pid,))
    p = cursor.fetchone()

    if not p:
        flash("Product not found", "danger")
        return redirect(url_for("products_page"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_qty":
            add_qty = int(request.form.get("add_qty") or 0)

            if add_qty > 0:
                cursor.execute(
                    "UPDATE product SET qty = qty + %s WHERE id = %s",
                    (add_qty, pid)
                )
                conn.commit()
                flash(f"Added {add_qty} units to {p['name']}", "success")
            else:
                flash("Invalid quantity", "warning")

            return redirect(url_for("products_page"))

        elif action == "edit_all":
            name = request.form.get("name")
            price = float(request.form.get("price") or 0)
            qty = int(request.form.get("qty") or 0)
            reorder = int(request.form.get("reorder_level") or 10)

            try:
                cursor.execute("""
                    UPDATE product 
                    SET name=%s, price=%s, qty=%s, reorder_level=%s
                    WHERE id=%s
                """, (name, price, qty, reorder, pid))

                conn.commit()
                flash("Product updated", "success")

            except:
                flash("Error updating product", "danger")

            return redirect(url_for("products_page"))

    cursor.close()
    conn.close()

    return render_template("edit_product.html", p=p)

# -------------------------
# ✅ DELETE PRODUCT (FIXED)
# -------------------------
@app.route("/product/delete/<int:pid>", methods=["POST"])
def delete_product(pid):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM product WHERE id = %s", (pid,))
        conn.commit()
        flash("Product deleted successfully", "info")
    except:
        flash("Error deleting product", "danger")

    cursor.close()
    conn.close()

    return redirect(url_for("products_page"))

# -------------------------
# BILLING
# -------------------------
@app.route("/billing", methods=["GET", "POST"])
def billing():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM product ORDER BY name")
    products = cursor.fetchall()

    bill_items = []
    total = 0

    if request.method == "POST":

        temp_items = []

        for p in products:
            field = f"qty_{p['id']}"

            try:
                sold_qty = int(request.form.get(field) or 0)
            except:
                sold_qty = 0

            if sold_qty > 0:
                if sold_qty > p["qty"]:
                    flash(f"Not enough stock for {p['name']}", "warning")
                else:
                    subtotal = sold_qty * p["price"]
                    temp_items.append((p, sold_qty, subtotal))

        if not temp_items:
            flash("No items sold.", "info")
            return redirect(url_for("billing"))

        cursor.execute(
            "INSERT INTO bill (created_at, total_amount) VALUES (%s,%s)",
            (datetime.now(), 0)
        )
        bill_id = cursor.lastrowid

        for p, sold_qty, subtotal in temp_items:

            cursor.execute(
                "UPDATE product SET qty = qty - %s WHERE id = %s",
                (sold_qty, p["id"])
            )

            cursor.execute(
                "INSERT INTO bill_item (bill_id, product_name, qty, price) VALUES (%s,%s,%s,%s)",
                (bill_id, p["name"], sold_qty, p["price"])
            )

            bill_items.append({
                "name": p["name"],
                "qty": sold_qty,
                "price": p["price"],
                "subtotal": subtotal
            })

            total += subtotal

        cursor.execute(
            "UPDATE bill SET total_amount=%s WHERE id=%s",
            (total, bill_id)
        )

        conn.commit()

    cursor.close()
    conn.close()

    return render_template("billing.html",
                           products=products,
                           bill_items=bill_items,
                           total=total,
                           store_name="7 Store",
                           store_address="Ganapathy, Coimbatore",
                           now=datetime.now())

# -------------------------
# EXPORT
# -------------------------
@app.route("/export")
def export_csv():
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM product", conn)

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    conn.close()

    return send_file(io.BytesIO(buf.getvalue().encode()),
                     mimetype="text/csv",
                     as_attachment=True,
                     download_name="stock_export.csv")

# -------------------------
# API
# -------------------------
@app.route("/api/products")
def api_products():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM product")
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(products)

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)