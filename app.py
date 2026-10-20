import os
import sqlite3
from datetime import date, timedelta

from flask import Flask, flash, g, jsonify, redirect, render_template, request, url_for

LOAN_DAYS = 14
FINE_PER_DAY = 2  # currency units per overdue day


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["DATABASE"] = db_path or os.environ.get(
        "DATABASE", os.path.join(app.root_path, "library.db")
    )

    # ---------- database helpers ----------
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        with app.open_resource("schema.sql") as f:
            get_db().executescript(f.read().decode("utf8"))

    # ---------- health (used by Docker / monitoring) ----------
    @app.route("/health")
    def health():
        get_db().execute("SELECT 1")
        return jsonify(status="ok")

    # ---------- dashboard ----------
    @app.route("/")
    def index():
        db = get_db()
        today = date.today().isoformat()
        stats = {
            "books": db.execute("SELECT COALESCE(SUM(copies),0) FROM books").fetchone()[0],
            "available": db.execute("SELECT COALESCE(SUM(available),0) FROM books").fetchone()[0],
            "titles": db.execute("SELECT COUNT(*) FROM books").fetchone()[0],
            "members": db.execute("SELECT COUNT(*) FROM members").fetchone()[0],
            "issued": db.execute(
                "SELECT COUNT(*) FROM issues WHERE return_date IS NULL"
            ).fetchone()[0],
            "overdue": db.execute(
                "SELECT COUNT(*) FROM issues WHERE return_date IS NULL AND due_date < ?",
                (today,),
            ).fetchone()[0],
        }
        base = (
            "SELECT i.*, b.title, m.name FROM issues i "
            "JOIN books b ON b.id=i.book_id JOIN members m ON m.id=i.member_id "
        )
        recent = db.execute(base + "ORDER BY i.id DESC LIMIT 5").fetchall()
        overdue = db.execute(
            base + "WHERE i.return_date IS NULL AND i.due_date < ? ORDER BY i.due_date LIMIT 5",
            (today,),
        ).fetchall()
        popular = db.execute(
            "SELECT b.title, b.author, COUNT(i.id) AS n FROM books b "
            "JOIN issues i ON i.book_id=b.id GROUP BY b.id ORDER BY n DESC LIMIT 5"
        ).fetchall()
        return render_template(
            "index.html", stats=stats, recent=recent, overdue=overdue, popular=popular
        )

    # ---------- sample data (for demos) ----------
    @app.route("/seed", methods=["POST"])
    def seed():
        db = get_db()
        if db.execute("SELECT COUNT(*) FROM books").fetchone()[0] > 0:
            flash("Sample data can only be loaded into an empty library.", "error")
            return redirect(url_for("index"))
        books = [
            ("Clean Code", "Robert C. Martin", "9780132350884", 3),
            ("The Pragmatic Programmer", "Andrew Hunt", "9780135957059", 2),
            ("Introduction to Algorithms", "Thomas H. Cormen", "9780262046305", 4),
            ("Python Crash Course", "Eric Matthes", "9781718502703", 3),
            ("The Phoenix Project", "Gene Kim", "9781942788294", 2),
            ("Docker Deep Dive", "Nigel Poulton", "9781916585256", 2),
            ("Wings of Fire", "A. P. J. Abdul Kalam", "9788173711466", 5),
            ("Database System Concepts", "Abraham Silberschatz", "9780078022159", 2),
        ]
        db.executemany(
            "INSERT INTO books (title, author, isbn, copies, available) VALUES (?,?,?,?,?)",
            [(t, a, i, c, c) for t, a, i, c in books],
        )
        members = [
            ("Aarav Kumar", "aarav@example.com", "9876543210"),
            ("Priya Sharma", "priya@example.com", "9876501234"),
            ("Karthik Raj", "karthik@example.com", "9876512345"),
            ("Divya Lakshmi", "divya@example.com", "9876523456"),
        ]
        db.executemany("INSERT INTO members (name, email, phone) VALUES (?,?,?)", members)
        today = date.today()
        # (book_id, member_id, days_ago, returned?)
        history = [(1, 1, 25, False), (3, 2, 20, True), (4, 3, 5, False), (1, 4, 3, False), (7, 2, 2, False)]
        for book_id, member_id, ago, returned in history:
            issued = today - timedelta(days=ago)
            due = issued + timedelta(days=LOAN_DAYS)
            ret = (issued + timedelta(days=10)).isoformat() if returned else None
            db.execute(
                "INSERT INTO issues (book_id, member_id, issue_date, due_date, return_date) VALUES (?,?,?,?,?)",
                (book_id, member_id, issued.isoformat(), due.isoformat(), ret),
            )
            if not returned:
                db.execute("UPDATE books SET available = available - 1 WHERE id=?", (book_id,))
        db.commit()
        flash("Sample data loaded.", "success")
        return redirect(url_for("index"))

    # ---------- books ----------
    @app.route("/books")
    def books():
        q = request.args.get("q", "").strip()
        db = get_db()
        if q:
            like = f"%{q}%"
            rows = db.execute(
                "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? ORDER BY title",
                (like, like, like),
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM books ORDER BY title").fetchall()
        return render_template("books.html", books=rows, q=q)

    @app.route("/books/add", methods=["GET", "POST"])
    def add_book():
        if request.method == "POST":
            title = request.form["title"].strip()
            author = request.form["author"].strip()
            isbn = request.form.get("isbn", "").strip() or None
            try:
                copies = int(request.form.get("copies", 1))
            except ValueError:
                copies = 0
            if not title or not author or copies < 1:
                flash("Title, author and at least 1 copy are required.", "error")
            else:
                try:
                    get_db().execute(
                        "INSERT INTO books (title, author, isbn, copies, available) VALUES (?,?,?,?,?)",
                        (title, author, isbn, copies, copies),
                    )
                    get_db().commit()
                    flash("Book added.", "success")
                    return redirect(url_for("books"))
                except sqlite3.IntegrityError:
                    flash("A book with this ISBN already exists.", "error")
        return render_template("book_form.html", book=None)

    @app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
    def edit_book(book_id):
        db = get_db()
        book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if book is None:
            flash("Book not found.", "error")
            return redirect(url_for("books"))
        if request.method == "POST":
            title = request.form["title"].strip()
            author = request.form["author"].strip()
            isbn = request.form.get("isbn", "").strip() or None
            try:
                copies = int(request.form.get("copies", book["copies"]))
            except ValueError:
                copies = 0
            on_loan = book["copies"] - book["available"]
            if not title or not author or copies < max(1, on_loan):
                flash(f"Title/author required and copies must be at least {max(1, on_loan)}.", "error")
            else:
                try:
                    db.execute(
                        "UPDATE books SET title=?, author=?, isbn=?, copies=?, available=? WHERE id=?",
                        (title, author, isbn, copies, copies - on_loan, book_id),
                    )
                    db.commit()
                    flash("Book updated.", "success")
                    return redirect(url_for("books"))
                except sqlite3.IntegrityError:
                    flash("A book with this ISBN already exists.", "error")
        return render_template("book_form.html", book=book)

    @app.route("/books/<int:book_id>/delete", methods=["POST"])
    def delete_book(book_id):
        db = get_db()
        active = db.execute(
            "SELECT COUNT(*) FROM issues WHERE book_id=? AND return_date IS NULL", (book_id,)
        ).fetchone()[0]
        if active:
            flash("Cannot delete: this book is currently issued.", "error")
        else:
            db.execute("DELETE FROM issues WHERE book_id=?", (book_id,))
            db.execute("DELETE FROM books WHERE id=?", (book_id,))
            db.commit()
            flash("Book deleted.", "success")
        return redirect(url_for("books"))

    # ---------- members ----------
    @app.route("/members")
    def members():
        q = request.args.get("q", "").strip()
        db = get_db()
        sql = (
            "SELECT m.*, (SELECT COUNT(*) FROM issues i "
            "WHERE i.member_id=m.id AND i.return_date IS NULL) AS loans FROM members m"
        )
        if q:
            like = f"%{q}%"
            rows = db.execute(
                sql + " WHERE m.name LIKE ? OR m.email LIKE ? ORDER BY m.name", (like, like)
            ).fetchall()
        else:
            rows = db.execute(sql + " ORDER BY m.name").fetchall()
        return render_template("members.html", members=rows, q=q)

    @app.route("/members/add", methods=["GET", "POST"])
    def add_member():
        if request.method == "POST":
            name = request.form["name"].strip()
            email = request.form.get("email", "").strip() or None
            phone = request.form.get("phone", "").strip() or None
            if not name:
                flash("Name is required.", "error")
            else:
                try:
                    get_db().execute(
                        "INSERT INTO members (name, email, phone) VALUES (?,?,?)", (name, email, phone)
                    )
                    get_db().commit()
                    flash("Member added.", "success")
                    return redirect(url_for("members"))
                except sqlite3.IntegrityError:
                    flash("A member with this email already exists.", "error")
        return render_template("member_form.html", member=None)

    @app.route("/members/<int:member_id>/edit", methods=["GET", "POST"])
    def edit_member(member_id):
        db = get_db()
        member = db.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
        if member is None:
            flash("Member not found.", "error")
            return redirect(url_for("members"))
        if request.method == "POST":
            name = request.form["name"].strip()
            email = request.form.get("email", "").strip() or None
            phone = request.form.get("phone", "").strip() or None
            if not name:
                flash("Name is required.", "error")
            else:
                try:
                    db.execute(
                        "UPDATE members SET name=?, email=?, phone=? WHERE id=?",
                        (name, email, phone, member_id),
                    )
                    db.commit()
                    flash("Member updated.", "success")
                    return redirect(url_for("members"))
                except sqlite3.IntegrityError:
                    flash("A member with this email already exists.", "error")
        return render_template("member_form.html", member=member)

    @app.route("/members/<int:member_id>/delete", methods=["POST"])
    def delete_member(member_id):
        db = get_db()
        active = db.execute(
            "SELECT COUNT(*) FROM issues WHERE member_id=? AND return_date IS NULL", (member_id,)
        ).fetchone()[0]
        if active:
            flash("Cannot delete: member still has unreturned books.", "error")
        else:
            db.execute("DELETE FROM issues WHERE member_id=?", (member_id,))
            db.execute("DELETE FROM members WHERE id=?", (member_id,))
            db.commit()
            flash("Member deleted.", "success")
        return redirect(url_for("members"))

    # ---------- issue / return ----------
    @app.route("/issues")
    def issues():
        status = request.args.get("status", "all")
        sql = (
            "SELECT i.*, b.title, m.name FROM issues i "
            "JOIN books b ON b.id=i.book_id JOIN members m ON m.id=i.member_id"
        )
        if status == "active":
            sql += " WHERE i.return_date IS NULL"
        elif status == "returned":
            sql += " WHERE i.return_date IS NOT NULL"
        sql += " ORDER BY i.id DESC"
        today = date.today()
        rows = []
        for r in get_db().execute(sql).fetchall():
            row = dict(r)
            due = date.fromisoformat(row["due_date"])
            end = date.fromisoformat(row["return_date"]) if row["return_date"] else today
            late_days = max((end - due).days, 0)
            row["overdue"] = row["return_date"] is None and late_days > 0
            row["fine"] = late_days * FINE_PER_DAY
            rows.append(row)
        return render_template("issues.html", issues=rows, status=status)

    @app.route("/issue", methods=["GET", "POST"])
    def issue_book():
        db = get_db()
        if request.method == "POST":
            try:
                book_id = int(request.form["book_id"])
                member_id = int(request.form["member_id"])
            except (KeyError, ValueError):
                flash("Select a book and a member.", "error")
                return redirect(url_for("issue_book"))
            book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
            member = db.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
            if book is None or member is None:
                flash("Invalid book or member.", "error")
            elif book["available"] < 1:
                flash("No copies of this book are available.", "error")
            else:
                today = date.today()
                db.execute(
                    "INSERT INTO issues (book_id, member_id, issue_date, due_date) VALUES (?,?,?,?)",
                    (book_id, member_id, today.isoformat(), (today + timedelta(days=LOAN_DAYS)).isoformat()),
                )
                db.execute("UPDATE books SET available = available - 1 WHERE id=?", (book_id,))
                db.commit()
                flash(f"Issued '{book['title']}' to {member['name']}. Due in {LOAN_DAYS} days.", "success")
                return redirect(url_for("issues"))
        books_available = db.execute(
            "SELECT * FROM books WHERE available > 0 ORDER BY title"
        ).fetchall()
        all_members = db.execute("SELECT * FROM members ORDER BY name").fetchall()
        return render_template("issue_form.html", books=books_available, members=all_members)

    @app.route("/return/<int:issue_id>", methods=["POST"])
    def return_book(issue_id):
        db = get_db()
        issue = db.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
        if issue is None or issue["return_date"] is not None:
            flash("This record is invalid or already returned.", "error")
        else:
            today = date.today()
            db.execute("UPDATE issues SET return_date=? WHERE id=?", (today.isoformat(), issue_id))
            db.execute("UPDATE books SET available = available + 1 WHERE id=?", (issue["book_id"],))
            db.commit()
            late = max((today - date.fromisoformat(issue["due_date"])).days, 0)
            msg = "Book returned."
            if late:
                msg += f" Late by {late} day(s). Fine: {late * FINE_PER_DAY}."
            flash(msg, "success")
        return redirect(url_for("issues"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
