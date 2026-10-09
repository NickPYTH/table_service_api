from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, Column, Integer, DateTime
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta


def main():
    base = declarative_base()

    class RowLock(base):
        __tablename__ = 'tables_rowlock'
        row_id = Column(Integer, primary_key=True)
        user_id = Column(Integer)
        locked_at = Column(DateTime)

    DATABASE_URL = "postgresql+psycopg2://root:111222333@localhost:5432/db"

    engine = create_engine(DATABASE_URL)

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        expired_time = datetime.now() - timedelta(minutes=5)
        deleted_count = session.query(RowLock).filter(RowLock.locked_at < expired_time).delete()

        session.commit()
        print(f"Удалено {deleted_count} устаревших блокировок")
    except Exception as e:
        session.rollback()
        print(f"Ошибка при очистке блокировок: {str(e)}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
