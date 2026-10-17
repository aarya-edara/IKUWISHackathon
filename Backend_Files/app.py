
import os
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from psycopg2 import errors
from jinja2 import ChoiceLoader, FileSystemLoader

from Database_Functions.UserDatabaseFunctions import (
    add_user,
    get_user,
    check_login
)


# ==========================================
# PROJECT FOLDERS
# ==========================================

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# HTML templates are in two different folders
TEMPLATE_DIR = APP_DIR / "templates"
FRONTEND_TEMPLATE_DIR = (
    BASE_DIR / "Frontend_Files" / "templates"
)

# CSS files are inside Backend_Files/static
STATIC_DIR = APP_DIR / "static"


# ==========================================
# DIAGNOSTICS
# ==========================================

print("\n========== FILE CHECK ==========")

print("Project folder:", BASE_DIR)

print("Backend templates:", TEMPLATE_DIR)
print("Frontend templates:", FRONTEND_TEMPLATE_DIR)

print(
    "Launch page exists:",
    (TEMPLATE_DIR / "Launch_Page.html").is_file()
)

print(
    "Calendar page exists:",
    (FRONTEND_TEMPLATE_DIR / "calendar.html").is_file()
)

print(
    "CSS folder exists:",
    STATIC_DIR.is_dir()
)

print("================================\n")


# ==========================================
# FLASK SETUP
# ==========================================

app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR)
)

# Allow Flask to find HTML files
# in both template folders

app.jinja_loader = ChoiceLoader([
    FileSystemLoader(str(TEMPLATE_DIR)),
    FileSystemLoader(str(FRONTEND_TEMPLATE_DIR))
])


# ==========================================
# FLASK SECURITY SETTINGS
# ==========================================

# Flask secret key
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]

# Session security
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("FLASK_COOKIE_SECURE", "false").lower() == "true"
)

# Enable CSRF protection
CSRFProtect(app)


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def launchPage():

    return render_template("Launch_Page.html")


# ==========================================
# REGISTER NEW USER
# ==========================================

@app.route("/register", methods=["POST"])
def register():

    email = request.form.get("email", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    try:

        user_id = add_user(
            email=email,
            username=username,
            password=password,
            individual_link=None
        )

    except ValueError as error:

        flash(str(error))
        return redirect(url_for("launchPage"))

    except errors.UniqueViolation:

        flash("Email or username already exists.")
        return redirect(url_for("launchPage"))

    # Log in newly registered user
    session.clear()
    session["user_id"] = user_id

    return redirect(url_for("dashboard"))


# ==========================================
# LOGIN EXISTING USER
# ==========================================

@app.route("/login", methods=["POST"])
def login():

    identifier = request.form.get(
        "username", ""
    ).strip()

    password = request.form.get("password", "")

    user_id = check_login(identifier, password)

    if user_id is None:

        flash("Incorrect username, email or password.")
        return redirect(url_for("launchPage"))

    # Create login session
    session.clear()
    session["user_id"] = user_id

    return redirect(url_for("dashboard"))


# ==========================================
# USER DASHBOARD / CALENDAR
# ==========================================

@app.route("/dashboard")
def dashboard():

    user_id = session.get("user_id")

    # If not logged in, return to homepage
    if user_id is None:
        return redirect(url_for("launchPage"))

    # Get logged-in user from database
    user = get_user(user_id)

    if user is None:

        session.clear()
        return redirect(url_for("launchPage"))

    # Display calendar page
    return render_template(
        "calendar.html",
        user=user
    )


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout", methods=["POST"])
def logout():

    session.clear()

    return redirect(url_for("launchPage"))


# ==========================================
# RUN FLASK LOCALLY
# ==========================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
