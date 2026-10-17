
import os
import re
import secrets
from pathlib import Path

import bcrypt
import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv


# ==========================================
# 1. CONNECT TO TIGERDATA
# ==========================================

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def connect_database():
    return psycopg2.connect(
        os.environ["TIMESCALE_SERVICE_URL"]
    )


# ==========================================
# 2. CREATE USER TABLE
# ==========================================

def create_user_table():

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS public.users (
                    user_number BIGINT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    individual_link TEXT
                );
            """)

    print("User table is ready!")


# ==========================================
# 3. GENERATE UNIQUE 9-DIGIT USER NUMBER
# ==========================================

def generate_user_number(connection):

    while True:

        # Generate a random 9-digit ID
        user_id = secrets.randbelow(900000000) + 100000000

        # Check whether the ID already exists
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 1
                FROM public.users
                WHERE user_number = %s;
            """, (user_id,))

            result = cursor.fetchone()

        if result is None:
            return user_id

        # Otherwise generate another ID


# ==========================================
# 4. VALIDATE REGISTRATION DETAILS
# ==========================================

def validate_registration(email, username, password):

    if not all(isinstance(value, str) for value in
               (email, username, password)):
        raise ValueError("Invalid registration details")

    email = email.strip().lower()
    username = username.strip()

    # Validate email
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Enter a valid email address")

    # Validate username
    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        raise ValueError(
            "Username must contain 3-30 characters "
            "using letters, numbers or underscores"
        )

    # Validate password
    if len(password) < 12:
        raise ValueError(
            "Password must be at least 12 characters"
        )

    if len(password.encode("utf-8")) > 72:
        raise ValueError(
            "Password must be no more than 72 bytes"
        )

    return email, username


# ==========================================
# 5. ADD NEW USER
# ==========================================

def add_user(email, username, password,
             individual_link=None, user_number=None):

    # Validate details
    email, username = validate_registration(
        email, username, password
    )

    if individual_link is not None:
        if not isinstance(individual_link, str):
            raise ValueError("Invalid individual link")

        if len(individual_link) > 2048:
            raise ValueError("Individual link is too long")

    # Hash password securely
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    # Retry only when a randomly generated ID collides
    for attempt in range(10):

        try:
            with connect_database() as connection:

                if user_number is None:
                    new_user_number = generate_user_number(
                        connection
                    )
                else:
                    new_user_number = user_number

                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO public.users (
                            user_number,
                            email,
                            username,
                            password_hash,
                            individual_link
                        )
                        VALUES (%s, %s, %s, %s, %s);
                    """, (
                        new_user_number,
                        email,
                        username,
                        password_hash,
                        individual_link
                    ))

            # The context manager commits on success
            print("User added successfully!")
            return new_user_number

        except errors.UniqueViolation as error:

            # Only retry for automatically generated ID
            if (
                user_number is None
                and error.diag.constraint_name == "users_pkey"
            ):
                continue

            # Duplicate email, username or manual ID
            raise

    raise RuntimeError(
        "Could not generate a unique user number"
    )


# ==========================================
# 6. FIND USER BY NUMBER
# ==========================================

def get_user(user_number):

    with connect_database() as connection:
        with connection.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute("""
                SELECT
                    user_number,
                    email,
                    username,
                    individual_link
                FROM public.users
                WHERE user_number = %s;
            """, (user_number,))

            result = cursor.fetchone()

    if result is None:
        return None

    return dict(result)


# ==========================================
# 7. CHECK LOGIN DETAILS
# ==========================================

def check_login(identifier, password):

    if not isinstance(identifier, str):
        return None

    if not isinstance(password, str):
        return None

    identifier = identifier.strip().lower()

    if not identifier or not password:
        return None

    # Determine whether login uses email or username
    if "@" in identifier:
        query = """
            SELECT user_number, password_hash
            FROM public.users
            WHERE LOWER(email) = %s;
        """
    else:
        query = """
            SELECT user_number, password_hash
            FROM public.users
            WHERE LOWER(username) = %s;
        """

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (identifier,))
            result = cursor.fetchone()

    if result is None:
        return None

    user_number, stored_hash = result

    # Verify password against stored hash
    try:
        password_matches = bcrypt.checkpw(
            password.encode("utf-8"),
            stored_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return None

    if password_matches:
        return user_number

    return None


# ==========================================
# 8. RUN DATABASE SETUP
# ==========================================

if __name__ == "__main__":

    create_user_table()
    print("SUCCESS! Connected to TigerData!")
