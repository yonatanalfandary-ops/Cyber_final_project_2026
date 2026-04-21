import hashlib
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

            # 2. STATIONS TABLE
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

            # 3. USER AUDIT TABLE
            # Tracks every login ('Joined') and logout ('Left') event per user per station.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_audit (
                    log_id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) NOT NULL,
                    station_id VARCHAR(50) NOT NULL,
                    action VARCHAR(20) NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 4. STATION AUDIT TABLE
            # Tracks every time a station comes Online or goes Offline.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS station_audit (
                    log_id INT AUTO_INCREMENT PRIMARY KEY,
                    station_id VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 5. SETTINGS TABLE
            # Stores global server-side configuration as key/value pairs.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    setting_key   VARCHAR(50)  PRIMARY KEY,
                    setting_value VARCHAR(255) NOT NULL
                )
            ''')

            # Seed default settings if they don't exist yet
            cursor.execute("""
                INSERT IGNORE INTO settings (setting_key, setting_value)
                VALUES ('privacy_screen', '0')
            """)

            conn.commit()
            conn.close()
            print("✅ Database Schema Loaded.")

        except mysql.connector.Error as err:
            print(f"❌ Database Init Error: {err}")

    @staticmethod
    def _hash_password(plain_text):
        """Returns the SHA-256 hex digest of a plain-text password string."""
        return hashlib.sha256(plain_text.encode('utf-8')).hexdigest()

    @staticmethod
    def _is_hashed(value):
        """Returns True if value already looks like a SHA-256 hex digest (64 hex chars)."""
        if not value or len(value) != 64:
            return False
        try:
            int(value, 16)
            return True
        except ValueError:
            return False

    def _migrate_plain_passwords(self):
        """
        One-time migration: finds any admin (root) accounts whose password is
        still stored as plain text and re-hashes them with SHA-256.
        Safe to call on every startup — already-hashed passwords are skipped.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT username, password FROM users WHERE role = 'root' AND password IS NOT NULL")
            rows = cursor.fetchall()
            for row in rows:
                if not self._is_hashed(row['password']):
                    hashed = self._hash_password(row['password'])
                    cursor.execute(
                        "UPDATE users SET password = %s WHERE username = %s",
                        (hashed, row['username'])
                    )
                    print(f"🔐 Migrated plain-text password for '{row['username']}' to SHA-256.")
            conn.commit()
        except Exception as e:
            print(f"❌ Password migration error: {e}")
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def ensure_root_exists(self):
        users = self.get_all_users()
        if not any(u['role'] == 'root' for u in users):
            print("⚠ No Root user found. Creating default 'admin'...")
            self.create_user("admin", "admin123", "System Administrator", "root")
        # Hash any plain-text passwords left over from before this update
        self._migrate_plain_passwords()

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

    def get_all_stations(self):
        """Fetches all stations and their current state for the Admin Dashboard."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT station_id, status, active_user AS `current_user` FROM stations")
            stations = cursor.fetchall()
            return stations
        except Exception as e:
            print(f"❌ Error fetching stations: {e}")
            return []
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

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

    # ==========================================
    # AUDIT LOGGING
    # ==========================================

    def log_user_action(self, username, station_id, action):
        """
        Inserts a row into user_audit.
        action must be 'Joined' or 'Left'.
        """
        if not username or not station_id:
            return
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = "INSERT INTO user_audit (username, station_id, action) VALUES (%s, %s, %s)"
            cursor.execute(sql, (username, station_id, action))
            conn.commit()
            print(f"📋 Audit: {username} {action} on {station_id}")
        except Exception as e:
            print(f"❌ User Audit Log Error: {e}")
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def log_station_status(self, station_id, status):
        """
        Inserts a row into station_audit.
        status must be 'Online' or 'Offline'.
        """
        if not station_id:
            return
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = "INSERT INTO station_audit (station_id, status) VALUES (%s, %s)"
            cursor.execute(sql, (station_id, status))
            conn.commit()
            print(f"📋 Audit: {station_id} went {status}")
        except Exception as e:
            print(f"❌ Station Audit Log Error: {e}")
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def get_user_audit(self, limit=300):
        """Returns user_audit rows ordered newest-first."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT username, station_id, action, timestamp "
                "FROM user_audit ORDER BY timestamp DESC LIMIT %s",
                (limit,)
            )
            rows = cursor.fetchall()
            # Convert datetime objects to strings for JSON serialisation
            for r in rows:
                if isinstance(r.get('timestamp'), datetime):
                    r['timestamp'] = r['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            return rows
        except Exception as e:
            print(f"❌ Fetch User Audit Error: {e}")
            return []
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def get_station_audit(self, limit=300):
        """Returns station_audit rows ordered newest-first."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT station_id, status, timestamp "
                "FROM station_audit ORDER BY timestamp DESC LIMIT %s",
                (limit,)
            )
            rows = cursor.fetchall()
            for r in rows:
                if isinstance(r.get('timestamp'), datetime):
                    r['timestamp'] = r['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            return rows
        except Exception as e:
            print(f"❌ Fetch Station Audit Error: {e}")
            return []
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def get_station_overview(self):
        """
        Returns each station's total all-time online duration in seconds,
        calculated by pairing every Online event with its next Offline event
        in station_audit.  Incomplete pairs (station still online) are skipped.
        """
        sql = """
            SELECT
                o.station_id,
                COALESCE(SUM(TIMESTAMPDIFF(SECOND, o.timestamp, f.timestamp)), 0) AS total_seconds
            FROM station_audit o
            INNER JOIN station_audit f
                ON  f.station_id = o.station_id
                AND f.status     = 'Offline'
                AND f.log_id     = (
                    SELECT MIN(log_id)
                    FROM   station_audit
                    WHERE  station_id = o.station_id
                    AND    status     = 'Offline'
                    AND    log_id     > o.log_id
                )
            WHERE o.status = 'Online'
            GROUP BY o.station_id
            ORDER BY total_seconds DESC
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql)
            rows = cursor.fetchall()
            # Convert Decimal/int to plain int for JSON serialisation
            for r in rows:
                r['total_seconds'] = int(r['total_seconds'])
            return rows
        except Exception as e:
            print(f"❌ Station Overview Error: {e}")
            return []
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def get_user_overview(self):
        """
        Returns each user's total all-time session duration in seconds,
        calculated by pairing every Joined event with its next Left event
        in user_audit.  Incomplete pairs (user still online) are skipped.
        """
        sql = """
            SELECT
                j.username,
                COALESCE(SUM(TIMESTAMPDIFF(SECOND, j.timestamp, l.timestamp)), 0) AS total_seconds
            FROM user_audit j
            INNER JOIN user_audit l
                ON  l.username = j.username
                AND l.action   = 'Left'
                AND l.log_id   = (
                    SELECT MIN(log_id)
                    FROM   user_audit
                    WHERE  username = j.username
                    AND    action   = 'Left'
                    AND    log_id   > j.log_id
                )
            WHERE j.action = 'Joined'
            GROUP BY j.username
            ORDER BY total_seconds DESC
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql)
            rows = cursor.fetchall()
            for r in rows:
                r['total_seconds'] = int(r['total_seconds'])
            return rows
        except Exception as e:
            print(f"❌ User Overview Error: {e}")
            return []
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def clear_user_audit(self):
        """Deletes all rows from user_audit."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("TRUNCATE TABLE user_audit")
            conn.commit()
            print("🗑️  User audit log cleared.")
            return True
        except Exception as e:
            print(f"❌ Clear User Audit Error: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def clear_station_audit(self):
        """Deletes all rows from station_audit."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("TRUNCATE TABLE station_audit")
            conn.commit()
            print("🗑️  Station audit log cleared.")
            return True
        except Exception as e:
            print(f"❌ Clear Station Audit Error: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    # ==========================================
    # SETTINGS
    # ==========================================

    def get_setting(self, key):
        """Returns the value for a setting key, or None if not found."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = %s", (key,))
            row = cursor.fetchone()
            return row['setting_value'] if row else None
        except Exception as e:
            print(f"❌ Get Setting Error: {e}")
            return None
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    def set_setting(self, key, value):
        """Inserts or updates a setting key/value pair."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO settings (setting_key, setting_value) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE setting_value = %s",
                (key, value, value)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ Set Setting Error: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected(): conn.close()

    # --- USER MANAGEMENT ---

    def create_user(self, username, password, full_name, role):
        if role == 'user':
            password = None
        elif password:  # Hash admin/root passwords before storing
            password = self._hash_password(password)

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
            cursor.execute("SELECT username, full_name, role, time_balance, face_encoding FROM users")
            users = cursor.fetchall()
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
            # Hash the plain-text password received from the client before
            # comparing — the database always stores the SHA-256 digest.
            hashed = self._hash_password(password) if password else ''
            sql = "SELECT * FROM users WHERE username = %s AND password = %s"
            cursor.execute(sql, (username, hashed))
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

            if field == 'role' and new_value not in ['root', 'user']:
                return False, "Role must be either 'root' or 'user'."

            # Hash new passwords before storing, or clear to NULL if empty
            if field == 'password':
                if new_value:
                    new_value = self._hash_password(new_value)
                else:
                    new_value = None  # Demoted to user — wipe the password

            sql = f"UPDATE users SET {field} = %s WHERE username = %s"
            cursor.execute(sql, (new_value, current_username))
            rows_affected = cursor.rowcount

            if field == 'role' and new_value == 'root':
                zero_sql = "UPDATE users SET time_balance = 0 WHERE username = %s"
                cursor.execute(zero_sql, (current_username,))
                print(f"⚖️ Database: Wiped time_balance to 0 for promoted root user '{current_username}'")

            conn.commit()

            if rows_affected > 0:
                return True, "Update success"
            return False, "User not found or no changes made"

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