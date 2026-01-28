import mysql.connector
import uuid

# DATABASE CONFIG
config = {
    "host": "localhost",
    "user": "root",
    "password": "BatTrot1!",
    "database": "rental_system"
}


def get_db_connection():
    return mysql.connector.connect(**config)


def create_user():
    print("\n--- ➕ CREATE NEW USER ---")
    username = input("Enter new username: ").strip()
    if not username:
        print("❌ Username cannot be empty.")
        return

    password = input("Enter password: ").strip()
    full_name = input("Enter full name: ").strip()

    print("Select Role: (1) User  (2) Admin")
    role = "root" if input("Choice: ").strip() == "2" else "user"

    user_id = str(uuid.uuid4())

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO users (user_id, username, full_name, password_hash, role, time_balance, face_encoding) 
        VALUES (%s, %s, %s, %s, %s, 0, NULL)
        """
        cursor.execute(sql, (user_id, username, full_name, password, role))
        conn.commit()
        print(f"✅ User '{username}' created successfully!")
        print("👉 Don't forget to run capture_face.py next.")

    except mysql.connector.Error as err:
        print(f"❌ Database Error: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected(): conn.close()


def delete_user():
    print("\n--- 🗑 DELETE USER ---")
    username = input("Enter username to DELETE: ").strip()

    confirm = input(f"⚠ Are you sure you want to delete '{username}'? (yes/no): ").lower()
    if confirm != "yes":
        print("❌ Action cancelled.")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM users WHERE username = %s", (username,))

        if cursor.rowcount > 0:
            conn.commit()
            print(f"✅ User '{username}' has been deleted.")
        else:
            print(f"❌ User '{username}' not found.")

    except mysql.connector.Error as err:
        print(f"❌ Database Error: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected(): conn.close()


def update_user():
    print("\n--- 📝 UPDATE USER DATA ---")
    username = input("Enter username to update: ").strip()

    # 1. Check if user exists first
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if not user:
            print(f"❌ User '{username}' not found.")
            conn.close()
            return

        print(f"\nEditing User: {username}")
        print("1. Full Name")
        print("2. Password")
        print("3. Role (user/root)")
        print("4. Time Balance")

        choice = input("Select column to update (1-4): ").strip()

        new_value = None
        column = None

        if choice == "1":
            column = "full_name"
            new_value = input("Enter new Full Name: ").strip()
        elif choice == "2":
            column = "password_hash"
            new_value = input("Enter new Password: ").strip()
        elif choice == "3":
            column = "role"
            print("Select Role: (1) User  (2) Admin")
            new_value = "root" if input("Choice: ").strip() == "2" else "user"
        elif choice == "4":
            column = "time_balance"
            try:
                new_value = float(input("Enter new Time Balance (minutes): "))
            except ValueError:
                print("❌ Invalid number.")
                conn.close()
                return
        else:
            print("❌ Invalid choice.")
            conn.close()
            return

        # Execute Update
        sql = f"UPDATE users SET {column} = %s WHERE username = %s"
        cursor.execute(sql, (new_value, username))
        conn.commit()
        print(f"✅ Updated {column} for '{username}' successfully.")

    except mysql.connector.Error as err:
        print(f"❌ Database Error: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected(): conn.close()


def main_menu():
    while True:
        print("\n=== 🛠 ADMIN USER MANAGER ===")
        print("1. Create New User")
        print("2. Delete User")
        print("3. Update User Column")
        print("4. Exit")

        choice = input("Select an option: ").strip()

        if choice == "1":
            create_user()
        elif choice == "2":
            delete_user()
        elif choice == "3":
            update_user()
        elif choice == "4":
            print("Exiting...")
            break
        else:
            print("Invalid option. Try again.")


if __name__ == "__main__":
    main_menu()