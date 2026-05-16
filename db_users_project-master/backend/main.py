from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
import models
import schemas
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Configure CORS
origins = [
    "http://94.159.100.3:3000",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def authenticate_user(db: Session, username: str, password: str):
    user = db.query(models.UserData).filter(
        models.UserData.username == username,
        models.UserData.password == password
    ).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return user

def check_unique_violation(error_msg: str) -> str:
    if "username" in error_msg.lower():
        return "Username already exists"
    return "Unique constraint violation"

@app.post("/users/", response_model=schemas.UserData)
def create_user(user: schemas.UserDataCreate, db: Session = Depends(get_db)):
    try:
        db_user = models.UserData(**user.model_dump())
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except IntegrityError as e:
        db.rollback()
        error_detail = check_unique_violation(str(e.orig))
        raise HTTPException(
            status_code=400,
            detail=error_detail
        )

@app.get("/users/", response_model=List[schemas.UserData])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = db.query(models.UserData).offset(skip).limit(limit).all()
    return users

@app.post("/users/auth", response_model=schemas.UserData)
def get_user_by_login_password(user_data: schemas.UserAuth, db: Session = Depends(get_db)):
    user = authenticate_user(db, user_data.username, user_data.password)
    return user

@app.put("/users/update", response_model=schemas.UserData)
def update_user(user_auth: schemas.UserAuth, user_update: schemas.UserDataUpdate, db: Session = Depends(get_db)):
    # Authenticate user first
    db_user = authenticate_user(db, user_auth.username, user_auth.password)
    
    try:
        # Update only the fields that are provided
        update_data = user_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_user, key, value)
        
        db.commit()
        db.refresh(db_user)
        return db_user
    except IntegrityError as e:
        db.rollback()
        error_detail = check_unique_violation(str(e.orig))
        raise HTTPException(
            status_code=400,
            detail=error_detail
        )

@app.delete("/users/delete", response_model=dict)
def delete_user(user_auth: schemas.UserAuth, db: Session = Depends(get_db)):
    try:
        # Authenticate user first
        db_user = authenticate_user(db, user_auth.username, user_auth.password)
        
        db.delete(db_user)
        db.commit()
        return {"message": "User deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to delete user"
        ) from e

@app.post("/users/get_users_by_project", response_model=schemas.ProjectUsersListResponse)
def get_users_by_project(user_auth: schemas.UserAuth, db: Session = Depends(get_db)):
    # Authenticate user first
    auth_user = authenticate_user(db, user_auth.username, user_auth.password)
    
    # Get all users with the same project
    project_users = db.query(models.UserData).filter(
        models.UserData.project == auth_user.project
    ).all()
    
    # Format response according to schema
    response_users = [
        schemas.ProjectUserResponse(
            username=user.username,
            other_data=user.other_data
        )
        for user in project_users
    ]
    
    return schemas.ProjectUsersListResponse(users=response_users) 