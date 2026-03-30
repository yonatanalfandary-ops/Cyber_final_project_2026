import mysql.connector
from mysql.connector import errorcode
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
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.db_name}")
            conn.close()

            conn = self.get_connection()
            cursor = conn.cursor()

            # 1. USERS TABLE
            cursor.execute('''
                            CREATE TABLE IF NOT EXISTS users (
                                user_id VARCHAR(36) PRIMARY KEY,
                                username VARCHAR(50) UNIQUE NOT NULL,
                                password VARCHAR(255),
                                full_name VARCHAR(100),
                                role VARCHAR(20) DEFAULT 'user', 
                                time_balance FLOAT DEFAULT 0,
                                face_encoding TEXT, 
                                created_at DATETIME
                            )
                        ''')

            # 2. STATIONS TABLE (Updated)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stations (
                    station_id VARCHAR(50) PRIMARY KEY,
                    station_name VARCHAR(100),
                    status VARCHAR(20) DEFAULT 'Offline',
                    last_seen DATETIME,
                    active_user VARCHAR(50) DEFAULT NULL,
                    revenue FLOAT DEFAULT 0.0
                )
            ''')

            # Safe Alters in case the table already existed without these columns
            try:
                cursor.execute("ALTER TABLE stations ADD COLUMN active_user VARCHAR(50) DEFAULT NULL")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE stations ADD COLUMN revenue FLOAT DEFAULT 0.0")
            except:
                pass

            conn.commit()
            conn.close()
            print("✅ Database Schema Loaded.")

        except mysql.connector.Error as err:
            print(f"❌ Database Init Error: {err}")

    def ensure_root_exists(self):
        users = self.get_all_users()
        if not any(u['role'] == 'root' for u in users):
            print("⚠ No Root user found. Creating default 'admin'...")
            self.create_user("admin", "admin123", "System Administrator", "root")

    # --- STATION MGMT & GAP LOGIC ---

    def check_station_exists(self, station_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM stations WHERE station_id = %s", (station_id,))
            exists = cursor.fetchone() is not None
            conn.close()
            return exists
        except:
            return False

    def get_all_station_ids(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT station_id FROM stations")
            ids = [row[0] for row in cursor.fetchall()]
            conn.close()
            return ids
        except:
            return []

    def create_gap_station(self):
        """Finds the lowest missing STATION_XX integer, creates it, and returns it."""
        existing_ids = self.get_all_station_ids()
        numbers = []
        for sid in existing_ids:
            if sid.startswith("STATION_"):
                try:
                    numbers.append(int(sid.split("_")[1]))
                except ValueError:
                    pass

        numbers.sort()
        new_num = 1
        for num in numbers:
            if num == new_num:
                new_num += 1
            elif num > new_num:
                break

        new_id = f"STATION_{new_num:02d}"

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = "INSERT INTO stations (station_id, station_name, status, revenue) VALUES (%s, %s, 'Online', 0.0)"
            cursor.execute(sql, (new_id, f"Station {new_num}"))
            conn.commit()
            conn.close()
            return new_id
        except Exception as e:
            print(f"❌ Gap Logic Error: {e}")
            return None

    def update_station_state(self, station_id, status, active_user=None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = "UPDATE stations SET status=%s, active_user=%s, last_seen=NOW() WHERE station_id=%s"
            cursor.execute(sql, (status, active_user, station_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Station Update Error: {e}")

    def add_station_revenue(self, station_id, amount):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE stations SET revenue = revenue + %s WHERE station_id = %s", (amount, station_id))
            conn.commit()
            conn.close()
        except Exception as e:
            pass

    def delete_station(self, station_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stations WHERE station_id = %s", (station_id,))
            conn.commit()
            conn.close()
            return True
        except:
            return False
    # --- USER MANAGEMENT ---

    def create_user(self, username, password, full_name, role):
        # --- NEW LOGIC: Enforce Password Rules ---
        # If it's a standard user, completely wipe the password before saving
        if role == 'user':
            password = None

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
            if err.errno == errorcode.ER_DUP_ENTRY:
                return False, "Username already exists!"
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

            # ADDED face_encoding to the SQL query
            cursor.execute("SELECT username, full_name, role, time_balance, face_encoding FROM users")
            users = cursor.fetchall()

            # DECODE the face_encoding from JSON so the client can use it
            for u in users:
                if u.get('face_encoding'):
                    u['face_encoding'] = json.loads(u['face_encoding'])

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

            # FORCE CASE SENSITIVITY FOR PASSWORD
            # We use 'BINARY' to ensure 'Pass' != 'pass'
            # (Username can stay case-insensitive if you prefer, or add BINARY there too)
            sql = "SELECT * FROM users WHERE username = %s AND BINARY password = %s"

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