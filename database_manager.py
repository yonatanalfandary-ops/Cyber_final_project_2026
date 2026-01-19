import mysql.connector
import json
import uuid
from datetime import datetime


class DatabaseManager:
    def __init__(self, host="localhost", user="root", password="BatTrot1!", database="rental_system"):
        """
        Connects to the MySQL Server.
        Change 'host' to your Server's IP if running on a different machine.
        """
        self.config = {
            "host": host,
            "user": user,
            "password": password,
            # "database": database # We add this later after checking if it exists
        }
        self.db_name = database
        self.init_database()

    def get_connection(self):
        """Creates a fresh connection to MySQL."""
        return mysql.connector.connect(database=self.db_name, **self.config)

    def init_database(self):
        """Creates the Database and Tables if they don't exist."""
        # 1. Connect without DB to create it
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.db_name}")
            conn.close()
        except mysql.connector.Error as err:
            print(f"❌ Connection Error: {err}")
            return

        # 2. Connect WITH DB to create tables
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Table: Users
            # We use VARCHAR(36) for UUIDs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(36) PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255),
                    face_encoding TEXT, 
                    created_at DATETIME
                )
            ''')

            # Table: Activity Logs (For later stages)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activity_logs (
                    log_id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(36),
                    action VARCHAR(100),
                    timestamp DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')

            conn.commit()
            conn.close()
            print("✅ MySQL Database initialized successfully.")

        except mysql.connector.Error as err:
            print(f"❌ Database Error: {err}")

    def register_user(self, username, password, face_encoding_list):
        """
        Saves a new user to MySQL.
        """
        user_id = str(uuid.uuid4())
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        face_json = json.dumps(face_encoding_list)

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            sql = "INSERT INTO users (user_id, username, password_hash, face_encoding, created_at) VALUES (%s, %s, %s, %s, %s)"
            val = (user_id, username, password, face_json, created_at)

            cursor.execute(sql, val)
            conn.commit()
            conn.close()

            print(f"✅ User {username} registered! ID: {user_id}")
            return user_id

        except mysql.connector.IntegrityError:
            print(f"⚠ Error: Username '{username}' already exists.")
            return None
        except mysql.connector.Error as err:
            print(f"❌ MySQL Error: {err}")
            return None

    def delete_user(self, username):
        """
        Deletes a user and their data from the database.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 1. Check if user exists first
            cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            result = cursor.fetchone()

            if not result:
                print(f"❌ User '{username}' not found.")
                return False

            # 2. Delete the user
            # Note: If you have activity logs, this might fail unless we delete logs first.
            # For now, since your logs are empty, this works fine.
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))
            conn.commit()
            conn.close()

            print(f"🗑️  SUCCESS: User '{username}' has been deleted.")
            return True

        except mysql.connector.Error as err:
            print(f"❌ MySQL Error: {err}")
            return False

    def get_all_users(self):
        """
        Fetches all users. Supports both Single-Face and Multi-Face storage.
        """
        users_data = []
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT username, face_encoding FROM users")
            rows = cursor.fetchall()

            for name, encoding_json in rows:
                if encoding_json:
                    data = json.loads(encoding_json)

                    # CHECK: Is this a single face (list of floats) or a gallery (list of lists)?
                    if len(data) > 0 and isinstance(data[0], list):
                        # It's a gallery (Multi-Shot)! Add each angle separately.
                        for angle in data:
                            users_data.append({"name": name, "encoding": angle})
                    else:
                        # It's a single face (Old style)
                        users_data.append({"name": name, "encoding": data})

            conn.close()
            return users_data

        except mysql.connector.Error as err:
            print(f"❌ Error fetching users: {err}")
            return []