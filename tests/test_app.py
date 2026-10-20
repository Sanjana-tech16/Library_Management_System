import pytest
from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    app.config["TESTING"] = True
    return app.test_client()


def add_book(client, **kw):
    data = {"title": "Clean Code", "author": "Robert Martin", "isbn": "111", "copies": "2"}
    data.update(kw)
    return client.post("/books/add", data=data, follow_redirects=True)


def add_member(client, **kw):
    data = {"name": "Asha", "email": "asha@example.com", "phone": "999"}
    data.update(kw)
    return client.post("/members/add", data=data, follow_redirects=True)


def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_add_and_search_book(client):
    assert b"Book added" in add_book(client).data
    assert b"Clean Code" in client.get("/books?q=clean").data
    assert b"No books found" in client.get("/books?q=zzz").data


def test_duplicate_isbn_rejected(client):
    add_book(client)
    assert b"already exists" in add_book(client).data


def test_add_member(client):
    assert b"Member added" in add_member(client).data
    assert b"Asha" in client.get("/members").data


def test_issue_and_return_flow(client):
    add_book(client, copies="1")
    add_member(client)
    assert b"Issued" in client.post("/issue", data={"book_id": 1, "member_id": 1}, follow_redirects=True).data
    # no copies left
    assert b"No copies" in client.post("/issue", data={"book_id": 1, "member_id": 1}, follow_redirects=True).data
    assert b"Book returned" in client.post("/return/1", follow_redirects=True).data
    # available again
    assert b"Issued" in client.post("/issue", data={"book_id": 1, "member_id": 1}, follow_redirects=True).data


def test_cannot_delete_issued_book(client):
    add_book(client)
    add_member(client)
    client.post("/issue", data={"book_id": 1, "member_id": 1})
    assert b"Cannot delete" in client.post("/books/1/delete", follow_redirects=True).data
    assert b"Cannot delete" in client.post("/members/1/delete", follow_redirects=True).data


def test_edit_and_delete_book(client):
    add_book(client)
    client.post("/books/1/edit", data={"title": "New Title", "author": "X", "isbn": "111", "copies": "3"})
    assert b"New Title" in client.get("/books").data
    assert b"Book deleted" in client.post("/books/1/delete", follow_redirects=True).data


def test_seed_and_dashboard(client):
    assert b"Load sample data" in client.get("/").data
    assert b"Sample data loaded" in client.post("/seed", follow_redirects=True).data
    page = client.get("/").data
    assert b"Overdue books" in page and b"Most popular books" in page
    assert b"Clean Code" in page
    # cannot seed twice
    assert b"only be loaded into an empty" in client.post("/seed", follow_redirects=True).data
    assert b"Books on loan" in client.get("/members").data
