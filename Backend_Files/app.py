
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

from Backend_Files.Database_Functions.UserDatabaseFunctions import (
    add_user,
    get_user,
    check_login
)

# Google calendar Imports
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
global SCOPES
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
import json
GOOGLE_CALLBACK = "https://www.almanac.luxe/google/callback"
import Backend_Files.CalendarLink_Functions.GoogleCalendar as GoogleCalendar

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
from flask import Flask, render_template
from Backend_Files.taskmanager import taskmanager_bp

app = Flask(__name__)
app.register_blueprint(taskmanager_bp)
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

# REGISTER NEW USER

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
    else:
        # Load Google credentials, or redirect to Google sign-in.
        creds = authenticateUserCredentials(user_id)

        if creds is None:
            return redirect(url_for("connect_google"))

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


# Google Calendar Import/Management Start -------------------------------------------- ↓↓↓

def authenticateUserCredentials(user_id):
    try:
        creds = None
        user = get_user(user_id)

        if user and user.get("google_token"):
            creds = Credentials.from_authorized_user_info(
                json.loads(user["google_token"]), SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                return None  # Flask will start Google sign-in

            save_google_token(user_id, creds.to_json())

        return creds

    except Exception as error:
        print("Google authentication failed:", error)
        return None

def save_google_token(user_id, creds):
    # todo:
    print("Save Token")

@app.route("/connect-google")
def connect_google():
    if "user_id" not in session:
        return redirect(url_for("launchPage"))

    flow = Flow.from_client_secrets_file(
        str(APP_DIR / "CalendarLink_Functions" / "credentials.json"),
        scopes=SCOPES,
        redirect_uri=GOOGLE_CALLBACK
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )

    session["google_code_verifier"] = flow.code_verifier
    session["google_state"] = state
    session["google_connect_user"] = session["user_id"]

    return redirect(auth_url)


@app.route("/google/callback")
def google_callback():
    state = session.pop("google_state", None)
    user_id = session.pop("google_connect_user", None)

    # Ensure this callback belongs to the user who started sign-in.
    if (
        not state
        or request.args.get("state") != state
        or user_id is None
        or session.get("user_id") != user_id
    ):
        return "Invalid sign-in session. Please try again.", 400

    if request.args.get("error") or not request.args.get("code"):
        return "Google Calendar connection was not completed.", 400

    flow = Flow.from_client_secrets_file(
        str(APP_DIR / "CalendarLink_Functions" / "credentials.json"),
        scopes=SCOPES,
        redirect_uri=GOOGLE_CALLBACK
    )

    flow.code_verifier = session.pop("google_code_verifier", None)

    if not flow.code_verifier:
        return "Sign-in session expired. Please connect Google again.", 400

    flow.fetch_token(code=request.args["code"])
    creds = flow.credentials

    save_google_token(user_id, creds.to_json())

    return redirect(url_for("dashboard"))

# Google Calendar Import/Management End  -------------------------------------------- ↑↑↑

# ==========================================
# RUN FLASK LOCALLY
# ==========================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
