
import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

# Find the main project folder
BASE_DIR = Path(__file__).resolve().parents[2]

# Load credentials from the project .env file
load_dotenv(BASE_DIR / ".env")

try:
    connection = psycopg2.connect(
        os.environ["TIMESCALE_SERVICE_URL"]
    )

    print("SUCCESS! Connected to TigerData!")

    connection.close()

except Exception as error:
    print("Connection failed:", error)


import os
from pathlib import Path

import bcrypt
import psycopg2
from dotenv import load_dotenv

#COnnect to tiger data

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def connect_database():
    return psycopg2.connect(
        os.environ["TIMESCALE_SERVICE_URL"]
    )

#create user table
def create_user_table():
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_number BIGINT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    individual_link TEXT
                );
            """)

    print("User table is ready!")


#generate user number

def generate_user_number():

    #
    # Add your own algorithm here.
    #
    # Requirements:
    # - Generate a unique user number
    # - Check that the number does not exist
    # - Return the number
    #
    # Example:
    # return 1001

    raise NotImplementedError(
        "User number algorithm not created yet"
    )


# add new user

def add_user(email, password, individual_link,
             user_number=None):

    if user_number is None:
        user_number = generate_user_number()

    # Hash password before storing
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO users
                (user_number, email,
                 password_hash, individual_link)
                VALUES (%s, %s, %s, %s);
            """, (
                user_number,
                email,
                password_hash,
                individual_link
            ))

    print("User added successfully!")
    return user_number


# find user
def get_user(user_number):

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT user_number, email,
                       individual_link
                FROM users
                WHERE user_number = %s;
            """, (user_number,))

            return cursor.fetchone()


# check login details

def check_login(email, password):

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT user_number, password_hash
                FROM users
                WHERE email = %s;
            """, (email,))

            result = cursor.fetchone()

    if result is None:
        return None

    user_number, stored_hash = result

    if bcrypt.checkpw(
        password.encode("utf-8"),
        stored_hash.encode("utf-8")
    ):
        return user_number

    return None



if __name__ == "__main__":
    create_user_table()
