# Implement a website via which users can “buy” and “sell” stocks.


import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show portfolio of stocks"""

    # Query database to display portfolio
    rows = db.execute("SELECT symbol, name, sum(buy) - sum(sell) AS shares, price, sum(total_buy) - sum(total_sell) AS total, person_id FROM history WHERE person_id = ? GROUP BY symbol HAVING shares > 0 AND total > 0;",
                      session["user_id"])

    # User reached route via POST (as by submitting a form via POST)
    # Allow users to buy more shares or sell shares of stocks they already own via index itself, without having to type stocks’ symbols manually
    if request.method == "POST":

        # Ensure shares was bought or sold
        if not any(request.form.getlist("new_shares")):
            return apology("missing shares", 400)

        # Shares that are bought or sold
        new_shares = list(filter(None, request.form.getlist("new_shares")))
        symbol = list(filter(None, request.form.getlist("symbol")))

        # Combine list of shares and symbol to become a list of dictionary
        values = dict(zip(symbol, new_shares))

        # Looping through the portfolio
        for i in range(len(rows)):

            # Ensure symbols are matched
            if rows[i]["symbol"] in symbol:

                # Lookup its quote
                quote = lookup(rows[i]["symbol"])

                # Buying the shares
                if int(values[rows[i]["symbol"]]) > rows[i]["shares"]:

                    # Insert into history table
                    db.execute("INSERT INTO history (symbol, name, buy, price, total_buy, person_id, datetime) VALUES (?, ?, ?, ?, ?, ?, datetime())",
                               quote["symbol"], quote["name"], int(values[rows[i]["symbol"]]) - rows[i]["shares"], quote["price"],
                               ((int(values[rows[i]["symbol"]]) - rows[i]["shares"]) * quote["price"]), session["user_id"])

                # Selling the shares
                else:

                    # Insert into history table
                    db.execute("INSERT INTO history (symbol, name, sell, price, total_sell, person_id, datetime) VALUES (?, ?, ?, ?, ?, ?, datetime())",
                               quote["symbol"], quote["name"], rows[i]["shares"] - int(values[rows[i]["symbol"]]), quote["price"],
                               ((rows[i]["shares"] - int(values[rows[i]["symbol"]])) * quote["price"]), session["user_id"])

        # Redirect the page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Default cash
        total = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        # Current cash
        cash = 0
        for row in rows:
            cash += row["total"]
        cash = total - cash

        # Display the portfolio
        return render_template("index.html", rows=rows, cash=cash, total=total, usd=usd)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        # Ensure valid symbol
        elif lookup(request.form.get("symbol")) == None:
            return apology("invalid symbol", 400)

        # Ensure share was submitted
        elif not request.form.get("shares"):
            return apology("missing shares", 400)

        # Ensure share was a valid digit
        elif not request.form.get("shares").isdigit():
            return apology("can't buy partial shares", 400)

        # Look up quote for symbol
        quote = lookup(request.form.get("symbol"))

        # Convert shares to float
        shares = float(request.form.get("shares"))

        # Ensure user can afford shares
        person = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])[0]
        if person["cash"] < (shares * quote["price"]):
            return apology("can't afford", 400)

        # Insert shares bought to database
        db.execute("INSERT INTO history (symbol, name, buy, price, total_buy, person_id, datetime) VALUES (?, ?, ?, ?, ?, ?, datetime())",
                   quote["symbol"], quote["name"], shares, quote["price"], (shares * quote["price"]), person["id"])

        # Redirect user to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query database for transactions
    rows = db.execute("SELECT * FROM history WHERE person_id = ? ORDER BY datetime DESC;", session["user_id"])

    # Display transactions
    return render_template("history.html", rows=rows, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Validate quote
        quote = lookup(request.form.get("symbol"))
        if not quote:
            return apology("missing symbol", 400)

        # Quote's information
        name = quote["name"]
        price = usd(quote["price"])
        symbol = quote["symbol"]

        # Display quote's information
        return render_template("quoted.html", name=name, price=price, symbol=symbol)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        username = request.form.get("username")
        existed_username = db.execute("SELECT username FROM users WHERE username = ?", username)

        # Ensure username was submitted
        if not username:
            return apology("must create username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must create password", 400)

        # Ensure password was confirmed
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        # Password and confirmed password was not the same
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("must confirm same password", 400)

        # Ensure new username
        elif existed_username and username == existed_username[0]["username"]:
            return apology("username was taken", 400)

        # Valid input
        else:

            # Insert new user to database
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                       username, generate_password_hash(request.form.get("password")))

            # Remember which user has registered
            session["user_id"] = db.execute("SELECT * FROM users WHERE username = ?", username)[0]["id"]

            # Redirect user to homepage
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        # Ensure share was submitted
        if not request.form.get("shares"):
            return apology("missing shares", 400)

        # Convert shares to float
        shares = float(request.form.get("shares"))

        # Ensure enough shares to sell
        if shares > db.execute("SELECT sum(buy) - sum(sell) AS shares FROM history WHERE symbol = ?;", request.form.get("symbol"))[0]["shares"]:
            return apology("too many shares", 400)

        # Look up quote for symbol
        quote = lookup(request.form.get("symbol"))

        # Query database for a person
        person = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])[0]

        # Insert transaction to database
        db.execute("INSERT INTO history (symbol, name, sell, price, total_sell, person_id, datetime) VALUES (?, ?, ?, ?, ?, ?, datetime())",
                   quote["symbol"], quote["name"], shares, quote["price"], (shares * quote["price"]), person["id"])

        # Redirect user to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Display owned symbol(s)
        symbols = db.execute("SELECT DISTINCT symbol FROM history WHERE person_id = ? ORDER BY symbol", session["user_id"])

        # Display a menu to sell symbols
        return render_template("sell.html", symbols=symbols)

if __name__ == "__main__":
    app.run()
