import os
import sqlite3
from decimal import Decimal
from pathlib import Path

from flask import Flask, current_app, flash, g, redirect, render_template, request, session, url_for


MENU_ITEMS = [
	("Harissa Chicken", "Citrus-marinated chicken, couscous, herbs, and preserved lemon.", 16.50, "Mains"),
	("Miso Mushroom Bowl", "Roasted mushrooms, sesame rice, pickled vegetables, and ginger miso.", 14.00, "Mains"),
	("Charred Halloumi", "Grilled halloumi, warm honey, smoked almonds, and mint.", 9.50, "Small plates"),
	("Crispy Potatoes", "Rosemary potatoes with whipped feta and spicy tomato relish.", 7.50, "Small plates"),
	("Orange Blossom Cake", "Olive oil cake, whipped yogurt, pistachio, and orange blossom.", 8.00, "Dessert"),
	("House Lemonade", "Fresh lemon, mint, and a touch of wildflower honey.", 4.50, "Drinks"),
]


def create_app(test_config=None):
	app = Flask(__name__, instance_relative_config=True)
	app.config.from_mapping(
		SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
		DATABASE=Path(app.instance_path) / "restaurant.sqlite3",
	)
	if test_config:
		app.config.update(test_config)

	Path(app.instance_path).mkdir(parents=True, exist_ok=True)
	init_db(app)

	@app.teardown_appcontext
	def close_db(_error=None):
		database = g.pop("database", None)
		if database is not None:
			database.close()

	@app.context_processor
	def inject_cart_count():
		return {"cart_count": sum(session.get("cart", {}).values())}

	@app.template_filter("money")
	def money(value):
		return f"${float(value):,.2f}"

	@app.get("/")
	def menu():
		items = query_db("SELECT * FROM menu_items WHERE available = 1 ORDER BY category, name")
		categories = []
		for item in items:
			if item["category"] not in categories:
				categories.append(item["category"])
		return render_template("menu.html", items=items, categories=categories)

	@app.post("/cart/add/<int:item_id>")
	def add_to_cart(item_id):
		item = query_db("SELECT id FROM menu_items WHERE id = ? AND available = 1", (item_id,), one=True)
		if item is None:
			flash("That menu item is no longer available.", "error")
			return redirect(url_for("menu"))
		cart = session.setdefault("cart", {})
		key = str(item_id)
		cart[key] = min(int(cart.get(key, 0)) + 1, 20)
		session.modified = True
		flash("Added to your order.", "success")
		return redirect(request.form.get("next") or url_for("menu"))

	@app.get("/cart")
	def cart():
		order_lines, subtotal = get_cart()
		return render_template("cart.html", order_lines=order_lines, subtotal=subtotal)

	@app.post("/cart/update")
	def update_cart():
		cart = {}
		for key, value in request.form.items():
			if not key.startswith("quantity-"):
				continue
			item_id = key.removeprefix("quantity-")
			try:
				quantity = int(value)
			except (TypeError, ValueError):
				quantity = 0
			if quantity > 0:
				cart[item_id] = min(quantity, 20)
		session["cart"] = cart
		flash("Order updated.", "success")
		return redirect(url_for("cart"))

	@app.route("/checkout", methods=["GET", "POST"])
	def checkout():
		order_lines, subtotal = get_cart()
		if not order_lines:
			flash("Add something delicious before checking out.", "error")
			return redirect(url_for("menu"))
		if request.method == "POST":
			name = request.form.get("name", "").strip()
			email = request.form.get("email", "").strip().lower()
			notes = request.form.get("notes", "").strip()
			errors = []
			if not 2 <= len(name) <= 80:
				errors.append("Please enter your name.")
			if "@" not in email or "." not in email.rsplit("@", 1)[-1] or len(email) > 120:
				errors.append("Please enter a valid email address.")
			if len(notes) > 500:
				errors.append("Notes must be 500 characters or fewer.")
			if errors:
				for error in errors:
					flash(error, "error")
				return render_template("checkout.html", order_lines=order_lines, subtotal=subtotal), 400
			database = get_db()
			cursor = database.execute(
				"INSERT INTO orders (customer_name, email, notes, total) VALUES (?, ?, ?, ?)",
				(name, email, notes, float(subtotal)),
			)
			order_id = cursor.lastrowid
			database.executemany(
				"INSERT INTO order_items (order_id, item_name, quantity, unit_price) VALUES (?, ?, ?, ?)",
				[(order_id, line["name"], line["quantity"], float(line["price"])) for line in order_lines],
			)
			database.commit()
			session.pop("cart", None)
			return redirect(url_for("order_confirmation", order_id=order_id))
		return render_template("checkout.html", order_lines=order_lines, subtotal=subtotal)

	@app.get("/orders/<int:order_id>")
	def order_confirmation(order_id):
		order = query_db("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
		if order is None:
			return render_template("not_found.html"), 404
		items = query_db("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
		return render_template("confirmation.html", order=order, items=items)

	return app


def get_db():
	if "database" not in g:
		g.database = sqlite3.connect(current_app.config["DATABASE"])
		g.database.row_factory = sqlite3.Row
	return g.database


def query_db(query, parameters=(), one=False):
	cursor = get_db().execute(query, parameters)
	rows = cursor.fetchall()
	cursor.close()
	return (rows[0] if rows else None) if one else rows


def init_db(app):
	with app.app_context():
		database = get_db()
		database.executescript(
			"""
			CREATE TABLE IF NOT EXISTS menu_items (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				name TEXT NOT NULL,
				description TEXT NOT NULL,
				price REAL NOT NULL CHECK (price >= 0),
				category TEXT NOT NULL,
				available INTEGER NOT NULL DEFAULT 1
			);
			CREATE TABLE IF NOT EXISTS orders (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				customer_name TEXT NOT NULL,
				email TEXT NOT NULL,
				notes TEXT NOT NULL DEFAULT '',
				total REAL NOT NULL,
				created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
			);
			CREATE TABLE IF NOT EXISTS order_items (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				order_id INTEGER NOT NULL REFERENCES orders(id),
				item_name TEXT NOT NULL,
				quantity INTEGER NOT NULL,
				unit_price REAL NOT NULL
			);
			"""
		)
		if database.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0] == 0:
			database.executemany("INSERT INTO menu_items (name, description, price, category) VALUES (?, ?, ?, ?)", MENU_ITEMS)
		database.commit()


def get_cart():
	cart = session.get("cart", {})
	if not cart:
		return [], Decimal("0")
	valid_ids = [int(item_id) for item_id in cart if str(item_id).isdigit()]
	if not valid_ids:
		return [], Decimal("0")
	placeholders = ",".join("?" for _ in valid_ids)
	items = query_db(f"SELECT * FROM menu_items WHERE id IN ({placeholders}) AND available = 1", valid_ids)
	order_lines = []
	subtotal = Decimal("0")
	for item in items:
		quantity = min(max(int(cart.get(str(item["id"]), 0)), 0), 20)
		if quantity:
			price = Decimal(str(item["price"]))
			order_lines.append({"id": item["id"], "name": item["name"], "description": item["description"], "price": price, "quantity": quantity, "line_total": price * quantity})
			subtotal += price * quantity
	return order_lines, subtotal


app = create_app()


if __name__ == "__main__":
	app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
