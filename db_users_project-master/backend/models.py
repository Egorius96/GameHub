from sqlalchemy import Column, Integer, String, JSON, UniqueConstraint
from database import Base

class UserData(Base):
    __tablename__ = "user_data"
 
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String, nullable=True, unique=True)
    password = Column(String, nullable=True)
    project = Column(String, nullable=True)
    other_data = Column(JSON, nullable=True) 