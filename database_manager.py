import mysql.connector
import json
import uuid
from datetime import datetime


class DatabaseManager:
    def __init__(self, host="localhost", user="root", password="BatTrot1!", database="rental_system"):
        self.config = {
            "host": host,
            "user": user,
            "password": password,
        }
        self.db_name = database
        self.init_database()
        self.ensure_root_exists()

    def get_connection(self):
        return mysql.connector.connect(database=self.db_name, **self.config)

    def init_database(self):
        """Creates Tables for Users and Stations (Matches your existing Schema)."""
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.db_name}")
            conn.close()

            conn = self.get_connection()
            cursor = conn.cursor()

            # 1. USERS TABLE - MATCHING YOUR EXISTING STRUCTURE
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(36) PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255),
                    role VARCHAR(20) DEFAULT 'user', 
                    time_balance FLOAT DEFAULT 0,
                    face_encoding TEXT, 
                    created_at DATETIME
                )
            ''')

            # 2. STATIONS TABLE
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stations (
                    station_id VARCHAR(50) PRIMARY KEY,
                    station_name VARCHAR(100),
                    status VARCHAR(20) DEFAULT 'offline',
                    last_seen DATETIME
                )
            ''')

            conn.commit()
            conn.close()
            print("✅ Database Schema Loaded.")

        except mysql.connector.Error as err:
            print(f"❌ Database Init Error: {err}")

    def ensure_root_exists(self):
        """Creates the default admin if missing."""
        users = self.get_all_users()
        if not any(u['role'] == 'root' for u in users):
            print("⚠ No Root user found. Creating default 'admin'...")
            self.create_user("admin", "admin123", "System Administrator", "root")

    # --- USER MANAGEMENT ---

    def create_user(self, username, password, full_name, role):
        # Generate UUID manually to match your table
        new_id = str(uuid.uuid4())
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            sql = "INSERT INTO users (user_id, username, password, full_name, role, time_balance, created_at) VALUES (%s, %s, %s, %s, %s, 0, %s)"
            cursor.execute(sql, (new_id, username, password, full_name, role, created_at))

            conn.commit()
            return True, "User created"
        except mysql.connector.Error as err:
            return False, str(err)
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

    def get_all_users(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT username, full_name, role, time_balance FROM users")
            users = cursor.fetchall()
            return users
        except Exception as e:
            print(f"Error fetching users: {e}")
            return []
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    # --- AUTHENTICATION & TIME ---

    def authenticate_user_login(self, username, password):
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Matches your 'password' column
            sql = "SELECT * FROM users WHERE username = %s AND password = %s"
            cursor.execute(sql, (username, password))
            user = cursor.fetchone()
            conn.close()

            if user:
                if user['face_encoding']:
                    user['face_encoding'] = json.loads(user['face_encoding'])
                return user
            return None
        except Exception as e:
            print(f"Auth Error: {e}")
            return None

    def add_time(self, username, minutes):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            # Prevent negative balance
            sql = "UPDATE users SET time_balance = GREATEST(0, time_balance + %s) WHERE username = %s"
            cursor.execute(sql, (minutes, username))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ Add Time Error: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def deduct_user_time(self, username, seconds_used):
        """Deducts time based on seconds used."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            minutes_to_deduct = seconds_used / 60.0

            sql = "UPDATE users SET time_balance = GREATEST(0, time_balance - %s) WHERE username = %s"
            cursor.execute(sql, (minutes_to_deduct, username))

            conn.commit()
            return True
        except Exception as e:
            print(f"❌ Time Deduction Error: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def update_user_field(self, current_username, field, new_value):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

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

    def update_user_face(self, username, face_data):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            face_json = json.dumps(face_data)
            sql = "UPDATE users SET face_encoding = %s WHERE username = %s"
            cursor.execute(sql, (face_json, username))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update Face Error: {e}")
            return False

    def get_active_renters(self):
        """Returns users with balance > 0 and face data."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT username, role, full_name, face_encoding, time_balance FROM users WHERE time_balance > 0 AND face_encoding IS NOT NULL")
            users = cursor.fetchall()

            for u in users:
                if u['face_encoding']:
                    u['face_encoding'] = json.loads(u['face_encoding'])
            return users
        except Exception as e:
            print(f"Fetch Error: {e}")
            return []
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    # --- STATION MGMT ---

    def register_station(self, station_id, station_name):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = "INSERT INTO stations (station_id, station_name, status) VALUES (%s, %s, 'offline')"
            cursor.execute(sql, (station_id, station_name))
            conn.commit()
            conn.close()
            return True
        except mysql.connector.Error:
            return False

    def activate_station(self, station_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE stations SET status='active', last_seen=NOW() WHERE station_id=%s", (station_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Station Activation Error: {e}")