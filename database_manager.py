import mysql.connector
import json
import uuid
from datetime import datetime
import bcrypt  # You might need to pip install bcrypt, or we can use simple strings for now if you prefer


class DatabaseManager:
    def __init__(self, host="localhost", user="root", password="BatTrot1!", database="rental_system"):
        self.config = {
            "host": host,
            "user": user,
            "password": password,
        }
        self.db_name = database
        self.init_database()
        self.ensure_root_exists()  # Auto-create the "HR Manager"

    def get_connection(self):
        return mysql.connector.connect(database=self.db_name, **self.config)

    def init_database(self):
        """Creates Tables for Users (with Roles) and Stations."""
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.db_name}")
            conn.close()

            conn = self.get_connection()
            cursor = conn.cursor()

            # 1. USERS TABLE (Now with Role and Balance)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(36) PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255),
                    role VARCHAR(20) DEFAULT 'user', 
                    time_balance INT DEFAULT 0,
                    face_encoding TEXT, 
                    created_at DATETIME
                )
            ''')
            # role: 'root' (HR) or 'user' (Employee)
            # time_balance: Minutes remaining

            # 2. STATIONS TABLE (The Computers)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stations (
                    station_id VARCHAR(50) PRIMARY KEY,
                    station_name VARCHAR(100),
                    status VARCHAR(20) DEFAULT 'offline',
                    last_seen DATETIME
                )
            ''')
            # status: 'active', 'offline', 'banned'

            conn.commit()
            conn.close()
            print("✅ Database Schema Updated (Users & Stations).")

        except mysql.connector.Error as err:
            print(f"❌ Database Error: {err}")

    def ensure_root_exists(self):
        """Creates the first 'HR' user if none exists."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE role = 'root'")
        if not cursor.fetchone():
            print("⚠ No Root User found. Creating default 'admin'...")
            # Default Root: admin / admin123 (You should change this later!)
            self.register_user("admin", "admin123", [], role="root")
        conn.close()

    def register_user(self, username, password, face_encoding_list, role="user"):
        """
        Only called by Root Client.
        """
        user_id = str(uuid.uuid4())
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        face_json = json.dumps(face_encoding_list)

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Simple password storage for now (Use hashing in production!)
            sql = "INSERT INTO users (user_id, username, password_hash, role, time_balance, face_encoding, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            val = (user_id, username, password, role, 0, face_json, created_at)

            cursor.execute(sql, val)
            conn.commit()
            conn.close()
            print(f"✅ User '{username}' ({role}) registered.")
            return True
        except mysql.connector.Error as err:
            print(f"❌ Registration Error: {err}")
            return False

    def register_station(self, station_id, station_name):
        """
        Only called by Admin Station.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = "INSERT INTO stations (station_id, station_name, status) VALUES (%s, %s, 'offline')"
            cursor.execute(sql, (station_id, station_name))
            conn.commit()
            conn.close()
            print(f"✅ Station '{station_name}' registered.")
            return True
        except mysql.connector.Error as err:
            print(f"❌ Station Error: {err}")
            return False

    def authenticate_user_login(self, username, password):
        """
        Stage A: Validates text credentials.
        Returns: User Dict (with face data) if success, None if fail.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)

            sql = "SELECT * FROM users WHERE username = %s AND password = %s"
            cursor.execute(sql, (username, password))
            user = cursor.fetchone()
            conn.close()

            if user:
                # Convert JSON face string back to list
                if user['face_encoding']:
                    user['face_encoding'] = json.loads(user['face_encoding'])
                return user
            return None
        except Exception as e:
            print(f"Auth Error: {e}")
            return None

    def activate_station(self, station_id):
        """
        Called when a user logs in. Sets station to 'active'.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE stations SET status='active', last_seen=NOW() WHERE station_id=%s", (station_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Station Activation Error: {e}")

    def update_user_face(self, username, face_encoding_list):
        """
        Updates the face data for an existing user.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            face_json = json.dumps(face_encoding_list)

            sql = "UPDATE users SET face_encoding = %s WHERE username = %s"
            cursor.execute(sql, (face_json, username))

            conn.commit()
            updated = cursor.rowcount > 0
            conn.close()

            if updated:
                print(f"✅ Updated face data for '{username}'")
                return True
            else:
                print(f"⚠ User '{username}' not found.")
                return False
        except Exception as e:
            print(f"❌ Update Error: {e}")
            return False

    def get_active_renters(self):
        """
        Returns a list of users who have time_balance > 0 AND have face data.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)

            # --- FIX: ADDED 'role' TO THIS QUERY ---
            cursor.execute(
                "SELECT username, role, full_name, face_encoding, time_balance FROM users WHERE time_balance > 0 AND face_encoding IS NOT NULL")

            users = cursor.fetchall()
            conn.close()

            # Parse the JSON face data
            for u in users:
                if u['face_encoding']:
                    u['face_encoding'] = json.loads(u['face_encoding'])
            return users
        except Exception as e:
            print(f"Fetch Error: {e}")
            return []

    def deduct_user_time(self, username, seconds_used):
        """
        Subtracts time from the user.
        Converts seconds to minutes for the database storage.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Convert seconds to minutes (e.g., 30 sec = 0.5 min)
            minutes_to_deduct = seconds_used / 60.0

            sql = "UPDATE users SET time_balance = GREATEST(0, time_balance - %s) WHERE username = %s"
            cursor.execute(sql, (minutes_to_deduct, username))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Time Deduction Error: {e}")
            return False

    def update_user_face(self, username, face_data):
        """
        Updates the face_encoding for an existing user.
        face_data is now a LIST of encodings (multiple angles).
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Convert list to JSON string for storage
            face_json = json.dumps(face_data)

            sql = "UPDATE users SET face_encoding = %s WHERE username = %s"
            cursor.execute(sql, (face_json, username))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update Face Error: {e}")
            return False

    def add_time(self, username, minutes):
        """Adds minutes to the user's existing balance."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            sql = "UPDATE users SET time_balance = GREATEST(0, time_balance + %s) WHERE username = %s"
            cursor.execute(sql, (minutes, username))
            conn.commit()

            # Verify the update happened
            if cursor.rowcount > 0:
                return True
            return False

        except Exception as e:
            print(f"❌ Add Time Error: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def update_user_field(self, current_username, field, new_value):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # CHANGED 'password_hash' -> 'password' in the allowed list
            if field not in ['full_name', 'password', 'username', 'role']:
                return False, "Invalid field"

            sql = f"UPDATE users SET {field} = %s WHERE username = %s"
            cursor.execute(sql, (new_value, current_username))
            conn.commit()

            if cursor.rowcount > 0:
                return True, "Update success"
            return False, "User not found"

        except Exception as e:
            return False, str(e)
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def get_all_users(self):
        """Returns a list of all users (username, full_name, role, time_balance)."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT username, full_name, role, time_balance FROM users")
            users = cursor.fetchall()
            return users
        except Exception as e:
            return []
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def create_user(self, username, password, full_name, role):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # REMOVED user_id from INSERT. The DB will handle it now.
            # CHANGED password_hash -> password
            sql = "INSERT INTO users (username, password, full_name, role, time_balance) VALUES (%s, %s, %s, %s, 0)"
            cursor.execute(sql, (username, password, full_name, role))
            conn.commit()
            return True, "User created"
        except Exception as e:
            return False, str(e)
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def delete_user(self, username):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))
            conn.commit()
            return True, "User deleted"
        except Exception as e:
            return False, str(e)
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()