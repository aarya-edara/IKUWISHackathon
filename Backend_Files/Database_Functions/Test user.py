
import uuid

from UserDatabaseFunctions import (
    add_user,
    get_user,
    check_login
)

# Generate unique test details
test_id = uuid.uuid4().hex[:8]

email = f"student_{test_id}@example.com"
username = f"student_{test_id}"
password = "TestPassword123!"
individual_link = "https://example.com/calendar/1"


# ==========================================
# TEST 1 - CREATE USER
# ==========================================

print("TEST 1: Creating user")

user_id = add_user(
    email=email,
    username=username,
    password=password,
    individual_link=individual_link
)

print("Generated ID:", user_id)

assert 100000000 <= user_id <= 999999999
print("PASS: Valid 9-digit user ID")


# ==========================================
# TEST 2 - RETRIEVE USER
# ==========================================

print("\nTEST 2: Retrieving user")

user = get_user(user_id)

assert user is not None
assert user["user_number"] == user_id
assert user["email"] == email
assert user["username"] == username
assert user["individual_link"] == individual_link

print("PASS: User details stored correctly")
print("Stored user:", user)


# ==========================================
# TEST 3 - LOGIN WITH USERNAME
# ==========================================

print("\nTEST 3: Username login")

assert check_login(username, password) == user_id

print("PASS: Username login successful")


# ==========================================
# TEST 4 - LOGIN WITH EMAIL
# ==========================================

print("\nTEST 4: Email login")

assert check_login(email, password) == user_id

print("PASS: Email login successful")


# ==========================================
# TEST 5 - INCORRECT PASSWORD
# ==========================================

print("\nTEST 5: Incorrect password")

assert check_login(username, "WrongPassword123!") is None

print("PASS: Incorrect password rejected")


# ==========================================
# TEST 6 - NON-EXISTENT USER
# ==========================================

print("\nTEST 6: Non-existent user")

assert get_user(9999999999) is None

print("PASS: Non-existent user handled correctly")


# ==========================================
# FINAL RESULTS
# ==========================================

print("\nALL 6 TESTS PASSED!")
