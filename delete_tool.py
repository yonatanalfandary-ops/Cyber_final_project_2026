from database_manager import DatabaseManager


def delete_user_tool():
    db = DatabaseManager()

    print("--- DELETE USER TOOL ---")

    # List current users so you know who to delete
    print("Current Users:")
    users = db.get_all_users()
    if not users:
        print(" (Database is empty)")
    else:
        # distinct names only (since we might have multi-shots)
        unique_names = set(u['name'] for u in users)
        for name in unique_names:
            print(f" - {name}")

    target = input("\nEnter username to delete (or 'ALL' to wipe everyone): ").strip()

    if target.upper() == "ALL":
        confirm = input("⚠ ARE YOU SURE? This deletes EVERYONE. (yes/no): ")
        if confirm.lower() == "yes":
            # We assume you want to loop through and delete them one by one
            # (Or you could execute 'TRUNCATE TABLE users' for a faster wipe)
            for name in unique_names:
                db.delete_user(name)
            print("Done.")
    else:
        db.delete_user(target)


if __name__ == "__main__":
    delete_user_tool()