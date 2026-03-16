from functools import cache
import sqlite3
import os

# This finds the folder where THIS script (data_db_handler.py) lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# This creates a path to the db file inside that same folder
DB_PATH = os.path.join(BASE_DIR, "game_data.db")

@cache
def get_db_connection():
    """Creates a fresh database connection to the correct absolute path."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def create_table():
    """
    creating a table containing:

    list of weapons
    list of ammo
    list of potions
    list of positions

    and giving them their default values

    :return:
    a built database with "info" rows
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS INVENTORY (
            Player_id INTEGER PRIMARY KEY,
            health INTEGER NOT NULL DEFAULT 400 CHECK (health <= 400),
            money INTEGER NOT NULL DEFAULT 200,
            
            weapon1 INTEGER NOT NULL DEFAULT 1,
            weapon2 INTEGER NOT NULL DEFAULT 2,
            weapon3 INTEGER NOT NULL DEFAULT 3,
            weapon4 INTEGER NOT NULL DEFAULT 4,
            weapon5 INTEGER NOT NULL DEFAULT 5,
            weapon6 INTEGER NOT NULL DEFAULT 0,
            weapon7 INTEGER NOT NULL DEFAULT 0,
            weapon8 INTEGER NOT NULL DEFAULT 0,
            weapon9 INTEGER NOT NULL DEFAULT 0,
            weapon10 INTEGER NOT NULL DEFAULT 0,
            
            ammo1 INTEGER NOT NULL DEFAULT 15,
            ammo2 INTEGER NOT NULL DEFAULT 3,
            ammo3 INTEGER NOT NULL DEFAULT 1000,
            ammo4 INTEGER NOT NULL DEFAULT 30,
            ammo5 INTEGER NOT NULL DEFAULT 10,
            ammo6 INTEGER NOT NULL DEFAULT 0,
            ammo7 INTEGER NOT NULL DEFAULT 0,
            ammo8 INTEGER NOT NULL DEFAULT 0,
            ammo9 INTEGER NOT NULL DEFAULT 0,
            ammo10 INTEGER NOT NULL DEFAULT 0,
            
            potion1 INTEGER NOT NULL DEFAULT 1,
            potion2 INTEGER NOT NULL DEFAULT 0,
            potion3 INTEGER NOT NULL DEFAULT 0,
            potion4 INTEGER NOT NULL DEFAULT 0,
            potion5 INTEGER NOT NULL DEFAULT 0,
            potion6 INTEGER NOT NULL DEFAULT 0,
            potion7 INTEGER NOT NULL DEFAULT 0,
            potion8 INTEGER NOT NULL DEFAULT 0,
            potion9 INTEGER NOT NULL DEFAULT 0,
            potion10 INTEGER NOT NULL DEFAULT 0,
            
            spawn_x integer NOT NULL DEFAULT 74010,
            spawn_y integer NOT NULL DEFAULT 32605
                )""")
        conn.commit()

STARTING_WEAPONS = [1, 2, 3, 4, 5, 0, 0, 0, 0, 0]
STARTING_AMMO    = [15, 3, 1000, 30, 10, 0, 0, 0, 0, 0]
STARTING_POTIONS = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]

def create_new_player(player_id):
    """Called ONLY when a player registers a new account."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO INVENTORY (
                Player_id,
                weapon1, weapon2, weapon3, weapon4, weapon5,
                weapon6, weapon7, weapon8, weapon9, weapon10,
                ammo1, ammo2, ammo3, ammo4, ammo5,
                ammo6, ammo7, ammo8, ammo9, ammo10,
                potion1, potion2, potion3, potion4, potion5,
                potion6, potion7, potion8, potion9, potion10
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (player_id, *STARTING_WEAPONS, *STARTING_AMMO, *STARTING_POTIONS))
        conn.commit()

def load_player(player_id):
    """Called when the player logs in and connects to the Region Server."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Select all columns explicitly to ensure the order is exactly what we expect

        cursor.execute("""
            SELECT 
                health, money, 
                weapon1, weapon2, weapon3, weapon4, weapon5, weapon6, weapon7, weapon8, weapon9, weapon10,
                ammo1, ammo2, ammo3, ammo4, ammo5, ammo6, ammo7, ammo8, ammo9, ammo10,
                potion1, potion2, potion3, potion4, potion5, potion6, potion7, potion8, potion9, potion10,
                spawn_x, spawn_y
            FROM INVENTORY 
            WHERE Player_id = ?
        """, (player_id,))

        row = cursor.fetchone()

        if row:
            # Slicing the row tuple into our parallel lists:

            # row[0] is health, row[1] is money
            # row[2:12] grabs the 10 weapons (indexes 2 through 11)
            # row[12:22] grabs the 10 potions (indexes 12 through 21)
            # row[22] is X pos, row[23] is Y pos

            return {
                "health": row[0],
                "money": row[1],
                "weapons": list(row[2:12]),
                "ammo": list(row[12:22]),
                "potions": list(row[22:32]),
                "spawn_x": row[32],
                "spawn_y": row[33]
            }

        return None  # Player not found


def save_player(player_id, health, money, weapons_list, ammo_list, potions_list, spawn_x, spawn_y):
    """
    overwrites the player's SQLite database row with their updated current live data
    triggered safely after the player leaves the game

    :param player_id:
    :param health:
    :param money:
    :param weapons_list:
    :param ammo_list:
    :param potions_list:
    :param spawn_x:
    :param spawn_y:
    :return:
    saved and updated data in the db based on player's actions in game - happens after disconnection
    """

    with get_db_connection() as conn:
        cursor = conn.cursor()

        query = """
            UPDATE INVENTORY SET 
                health = ?, money = ?,
                weapon1 = ?, weapon2 = ?, weapon3 = ?, weapon4 = ?, weapon5 = ?,
                weapon6 = ?, weapon7 = ?, weapon8 = ?, weapon9 = ?, weapon10 = ?,
                ammo1 = ?, ammo2 = ?, ammo3 = ?, ammo4 = ?, ammo5 = ?,
                ammo6 = ?, ammo7 = ?, ammo8 = ?, ammo9 = ?, ammo10 = ?,
                potion1 = ?, potion2 = ?, potion3 = ?, potion4 = ?, potion5 = ?,
                potion6 = ?, potion7 = ?, potion8 = ?, potion9 = ?, potion10 = ?,
                spawn_x = ?, spawn_y = ?
            WHERE Player_id = ?
        """

        # We combine our variables and lists into one master list for SQLite
        # The order here MUST match the order of the '?' in the query above!
        params = [health, money] + weapons_list + ammo_list + potions_list + [spawn_x, spawn_y, player_id]

        cursor.execute(query, params)
        conn.commit()


def wipe_all_game_data():
    """Empties all rows from the game database for clean testing."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM INVENTORY")

        conn.commit()
        print("Game database wiped clean! Ready for new test accounts.")

def reset_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS INVENTORY")
        conn.commit()


#reset_db()
#create_table()
#wipe_all_game_data()