import sqlite3

connection = sqlite3.connect("Auth.db")
cursor = connection.cursor()


def create_table():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS USERS
        (user_ID INTEGER PRIMARY KEY AUTOINCREMENT, 
         username TEXT UNIQUE NOT NULL, 
         password TEXT NOT NULL)
            """)
    connection.commit()

def insert_game(username, password):
    # This function now correctly handles the automatic ID
    try:
        cursor.execute("INSERT INTO DATABASE (username, password) VALUES (?, ?)", (username, password))
        connection.commit()
    except sqlite3.IntegrityError:
        print(f"Error: Username '{username}' already exists!")

def executemany_game():
    data = [
        ('Alex_Runner', 'speed123'),
        ('Maya_Dev', 'coding_life'),
        ('Jordan_QA', 'bug_hunter_1')
    ]
    cursor.executemany("INSERT INTO DATABASE (username, password) VALUES (?, ?)", data)
    connection.commit()

def delete_all():
    cursor.execute("""DELETE FROM USERS""")

    cursor.execute("DELETE FROM sqlite_sequence WHERE name='USERS'")

    connection.commit()

def delete_all_sessions():
    cursor.execute("""DELETE FROM SESSIONS""")

    cursor.execute("DELETE FROM sqlite_sequence WHERE name='SESSIONS'")

    connection.commit()
def delete_db():
    cursor.execute("""Drop table Database""")
    connection.commit()

# --- EXECUTION ---
# This forces the table to reset its rules every time you run the script
# cursor.execute("DROP TABLE IF EXISTS USERS")

create_table()
delete_all()
delete_all_sessions()

# cursor.execute("INSERT INTO DATABASE (username, password) VALUES (?, ?)", ('Idan', 123))
#connection.commit()
# executemany_game()
# print("Current Database Content:")
# # We fetch the actual data to ensure it isn't None
# cursor.execute("SELECT user_id, username, password FROM DATABASE ORDER BY user_id")
# rows = cursor.fetchall()
#
# if not rows:
#     print("The database is empty!")
# else:
#     for row in rows:
#         print(f"ID: {row[0]} | User: {row[1]} | Pass: {row[2]}")

connection.close()
