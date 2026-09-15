import sqlite3

import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE": tmp_path / "test.sqlite3"})
    with app.test_client() as client:
        yield client


def test_menu_is_seeded(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Harissa Chicken" in response.data
    assert b"Today\xe2\x80\x99s table" in response.data


def test_empty_checkout_redirects_to_menu(client):
    response = client.get("/checkout", follow_redirects=True)
    assert response.status_code == 200
    assert b"Add something delicious" in response.data


def test_invalid_checkout_does_not_create_order(client, tmp_path):
    client.post("/cart/add/1")
    response = client.post("/checkout", data={"name": "", "email": "bad"})
    assert response.status_code == 400
    with sqlite3.connect(tmp_path / "test.sqlite3") as database:
        assert database.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_customer_can_place_order_and_cart_is_cleared(client, tmp_path):
    client.post("/cart/add/1")
    client.post("/cart/add/1")
    response = client.post("/checkout", data={"name": "Mina Chen", "email": "mina@example.com", "notes": "Extra herbs"})
    assert response.status_code == 302
    assert "/orders/" in response.headers["Location"]
    confirmation = client.get(response.headers["Location"])
    assert confirmation.status_code == 200
    assert b"Mina Chen" in confirmation.data
    with client.session_transaction() as session:
        assert "cart" not in session
    with sqlite3.connect(tmp_path / "test.sqlite3") as database:
        assert database.execute("SELECT customer_name, total FROM orders").fetchone() == ("Mina Chen", 33.0)
        assert database.execute("SELECT quantity FROM order_items").fetchone()[0] == 2
