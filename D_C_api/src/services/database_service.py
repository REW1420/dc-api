import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from utils.config import USER, PASSWORD, HOST, PORT, DBNAME


def get_db_connection():
    try:
        connection = psycopg2.connect(
            user=USER,
            password=PASSWORD,
            host=HOST,
            port=PORT,
            dbname=DBNAME
        )
        return connection
    except Exception as e:
        print(f"❌ Error al conectar a la base de datos: {e}")
        raise


def execute_query(query, params=None, fetch=False):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params)

        if fetch:
            return cursor.fetchall()
        else:
            conn.commit()
            return None
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()


def insert_many(table, data):
    if not data:
        return

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        columns = data[0].keys()
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(', ').join(map(sql.Identifier, columns)),
            sql.SQL(', ').join(sql.Placeholder() * len(columns))
        )

        cursor.executemany(query, [tuple(item.values()) for item in data])
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()


def insert_many_resolving_fk(table, data):
    if not data:
        return

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        for row in data:
            columns = []
            values = []
            placeholders = []

            for k, v in row.items():
                columns.append(sql.Identifier(k))
                if isinstance(v, str) and v.startswith("(SELECT"):
                    placeholders.append(sql.SQL(v))
                else:
                    placeholders.append(sql.Placeholder())
                    values.append(v)

            query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table),
                sql.SQL(", ").join(columns),
                sql.SQL(", ").join(placeholders)
            )
            cursor.execute(query, values)

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
