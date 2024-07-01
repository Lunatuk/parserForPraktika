import psycopg2
import dotenv
import os

def migrate_db():
    dotenv.load_dotenv()

    dbname = os.environ.get('DB_NAME')
    dbuser = os.environ.get('DB_USER')
    dbpassword = os.environ.get('DB_PASSWORD')
    dbhost = os.environ.get('DB_HOST')
    dbport = os.environ.get('DB_PORT')

    conn = psycopg2.connect(
        dbname=dbname,
        user=dbuser,
        password=dbpassword,
        host=dbhost,
        port=dbport
    )
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vacancies (
        id SERIAL PRIMARY KEY,
        company VARCHAR(255),
        vacancy VARCHAR(255),
        location VARCHAR(255),
        salary VARCHAR(255),
        skills TEXT,
        link TEXT,
        description TEXT
    );
    """)
    
    print("БДшка создана иди глянь в pgAdmin")
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    migrate_db()
