from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum
from sqlalchemy import text
import os
from dotenv import load_dotenv
from db_connection import get_db_connection
from jwt_wrapper import token_required
from jose import jwt

load_dotenv()

app = FastAPI(
    title="Lost & Found API",
    description="API for Lost and Found Management System",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv('SECRET_KEY')

# ===========================================================
# ENUMS
# ===========================================================
class RequestType(str, Enum):
    lost = "lost"
    found = "found"

class RequestStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

class UserRole(str, Enum):
    student = "student"
    faculty = "faculty"
    admin = "admin"
    alumni = "alumni"
    public = "public"

# ===========================================================
# PYDANTIC MODELS
# ===========================================================
class LostFoundRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000)
    type: RequestType

class LostFoundResponse(BaseModel):
    lnf_id: int
    user_id: str
    user_role: str
    name: str
    email: str
    department: str
    description: str
    type: str
    status: str
    created_at: datetime

# ===========================================================
# HELPER: GET USER FROM TOKEN
# ===========================================================
def get_user_from_token(request: Request):
    """
    Extract user information from JWT token
    """
    try:
        if hasattr(request.state, 'decoded_token'):
            decoded = request.state.decoded_token
        else:
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                raise HTTPException(status_code=401, detail="Authorization header missing")
            
            token = auth_header.split(" ")[1]
            decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        
        user_data = {
            "user_id": decoded.get("user_id"),
            "user_role": decoded.get("user_role"),
            "name": decoded.get("name"),
            "email": decoded.get("email"),
            "department": decoded.get("department", "N/A")
        }
        
        if not all([user_data["user_id"], user_data["user_role"], user_data["name"], user_data["email"]]):
            raise HTTPException(
                status_code=400,
                detail=f"Incomplete user data in JWT. Required: user_id, user_role, name, email"
            )
        
        return user_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Failed to extract user data: {str(e)}")

# ===========================================================
# POST: SUBMIT NEW REQUEST (JWT PROTECTED)
# ===========================================================
@app.post("/api/v1/lost-found/submit", status_code=201)
@token_required
async def submit_request(request: Request, lost_found: LostFoundRequest):
    """
    Submit a new Lost or Found item request.
    User only provides: description, type (lost/found)
    Other fields auto-fetched from JWT token.
    """
    engine = get_db_connection()
    
    try:
        # Get user data from JWT
        user_data = get_user_from_token(request)
        
        table_name = os.getenv("TABLE_NAME", "lost_and_found")
        
        query = text(f"""
            INSERT INTO {table_name} 
            (user_id, user_role, name, email, department, description, type, status, created_at)
            VALUES (:user_id, :user_role, :name, :email, :department, :description, :type, :status, :created_at)
            RETURNING lnf_id, user_id, user_role, name, email, department, description, type, status, created_at;
        """)
        
        values = {
            "user_id": user_data["user_id"],
            "user_role": user_data["user_role"],
            "name": user_data["name"],
            "email": user_data["email"],
            "department": user_data["department"],
            "description": lost_found.description,
            "type": lost_found.type.value,
            "status": RequestStatus.pending.value,
            "created_at": datetime.now()
        }
        
        with engine.connect() as conn:
            result = conn.execute(query, values)
            inserted = result.fetchone()
            conn.commit()
            
            return {
                "success": True,
                "message": "Request submitted successfully. Admin will review it soon.",
                "data": dict(inserted._mapping)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit request: {str(e)}")

# ===========================================================
# GET: ALL APPROVED REQUESTS (JWT PROTECTED)
# ===========================================================
@app.get("/api/v1/lost-found/all")
@token_required
async def get_all_requests(
    request: Request,
    type: Optional[RequestType] = Query(None, description="Filter by 'lost' or 'found'")
):
    """
    Get all approved Lost/Found requests.
    Public can see approved items after admin approval.
    """
    engine = get_db_connection()
    
    try:
        user_data = get_user_from_token(request)
        table_name = os.getenv("TABLE_NAME", "lost_and_found")
        
        if type:
            query = text(f"""
                SELECT lnf_id, user_id, user_role, name, email, department, description, type, status, created_at
                FROM {table_name}
                WHERE status = :status AND type = :type
                ORDER BY created_at DESC;
            """)
            params = {"status": RequestStatus.approved.value, "type": type.value}
        else:
            query = text(f"""
                SELECT lnf_id, user_id, user_role, name, email, department, description, type, status, created_at
                FROM {table_name}
                WHERE status = :status
                ORDER BY created_at DESC;
            """)
            params = {"status": RequestStatus.approved.value}
        
        with engine.connect() as conn:
            result = conn.execute(query, params)
            results = result.fetchall()
            
            return {
                "success": True,
                "count": len(results),
                "data": [dict(row._mapping) for row in results]
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch requests: {str(e)}")

# ===========================================================
# GET: USER'S OWN REQUESTS (JWT PROTECTED)
# ===========================================================
@app.get("/api/v1/lost-found/my-requests")
@token_required
async def get_my_requests(request: Request):
    """
    Fetch all requests submitted by the logged-in user.
    User identified from JWT token (no rollno parameter needed).
    """
    engine = get_db_connection()
    
    try:
        # Get user data from JWT
        user_data = get_user_from_token(request)
        user_id = user_data["user_id"]
        
        table_name = os.getenv("TABLE_NAME", "lost_and_found")
        
        query = text(f"""
            SELECT lnf_id, user_id, user_role, name, email, department, description, type, status, created_at
            FROM {table_name}
            WHERE user_id = :user_id
            ORDER BY created_at DESC;
        """)
        
        with engine.connect() as conn:
            result = conn.execute(query, {"user_id": user_id})
            results = result.fetchall()
            
            return {
                "success": True,
                "count": len(results),
                "data": [dict(row._mapping) for row in results]
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user requests: {str(e)}")

# ===========================================================
# PUT: UPDATE STATUS - ADMIN (JWT PROTECTED)
# ===========================================================
@app.put("/api/v1/admin/update-status/{request_id}")
@token_required
async def update_request_status(
    request: Request,
    request_id: int,
    status: RequestStatus = Query(..., description="New status: 'approved' or 'rejected'")
):
    """
    Admin: Update the status of a Lost/Found request.
    Can approve or reject pending requests.
    """
    engine = get_db_connection()
    
    try:
        # Verify user (optional: check if admin)
        user_data = get_user_from_token(request)
        # if user_data["user_role"] != "admin":
        #     raise HTTPException(status_code=403, detail="Admin access required")
        
        table_name = os.getenv("TABLE_NAME", "lost_and_found")
        
        # Check if request exists
        check_query = text(f"""
            SELECT lnf_id, status 
            FROM {table_name} 
            WHERE lnf_id = :request_id
        """)
        
        with engine.connect() as conn:
            result = conn.execute(check_query, {"request_id": request_id})
            existing = result.fetchone()
            
            if not existing:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Request with ID {request_id} not found"
                )
            
            # Update status
            update_query = text(f"""
                UPDATE {table_name}
                SET status = :status
                WHERE lnf_id = :request_id
                RETURNING lnf_id, user_id, user_role, name, email, department, description, type, status, created_at
            """)
            
            result = conn.execute(
                update_query, 
                {"status": status.value, "request_id": request_id}
            )
            updated_row = result.fetchone()
            conn.commit()
            
            return {
                "success": True,
                "message": f"Request status updated to '{status.value}' successfully",
                "data": dict(updated_row._mapping)
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")

# ===========================================================
# SETUP: CREATE TABLE
# ===========================================================
@app.post("/api/v1/setup/create-table")
async def create_table():
    """
    Creates the lost_and_found table in database.
    Run this once to setup the database.
    WARNING: This will DROP existing table if it exists!
    """
    engine = get_db_connection()
    
    try:
        table_name = os.getenv("TABLE_NAME", "lost_and_found")
        
        query = text(f"""
            -- Drop table if exists
            DROP TABLE IF EXISTS {table_name};
            
            -- Create table with new structure
            CREATE TABLE {table_name} (
                lnf_id SERIAL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                user_role VARCHAR(20) NOT NULL,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) NOT NULL,
                department VARCHAR(100),
                description TEXT NOT NULL,
                type VARCHAR(10) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Create indexes
            CREATE INDEX idx_lnf_user_id ON {table_name}(user_id);
            CREATE INDEX idx_lnf_user_role ON {table_name}(user_role);
            CREATE INDEX idx_lnf_status ON {table_name}(status);
            CREATE INDEX idx_lnf_type ON {table_name}(type);
            CREATE INDEX idx_lnf_email ON {table_name}(email);
        """)
        
        with engine.connect() as conn:
            conn.execute(query)
            conn.commit()
            
        return {
            "success": True,
            "message": f"Table '{table_name}' created successfully with indexes"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create table: {str(e)}")

# ===========================================================
# TEMPORARY: TOKEN GENERATION FOR TESTING
# ===========================================================
@app.post("/api/v1/auth/generate-test-token")
async def generate_test_token(
    user_id: str,
    user_role: str,
    name: str,
    email: str,
    department: str = "N/A"
):
    """
    TEMPORARY: Generate JWT token for testing.
    ⚠️ REMOVE IN PRODUCTION!
    """
    try:
        from jwt_wrapper import generate_token
        
        user_data = {
            "user_id": user_id,
            "user_role": user_role,
            "name": name,
            "email": email,
            "department": department
        }
        
        client_id = os.getenv('STATIC_CLIENT_ID')
        client_secret = os.getenv('STATIC_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            raise HTTPException(status_code=500, detail="Client credentials not configured")
        
        token = generate_token(client_id, client_secret, user_data)
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        
        return {
            "success": True,
            "token": token,
            "decoded_payload": decoded,
            "usage": {
                "postman": "Authorization: Bearer " + token
            },
            "note": "⚠️ Remove this endpoint in production!"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate token: {str(e)}")

# ===========================================================
# HEALTH CHECK (NO JWT REQUIRED)
# ===========================================================
@app.get("/")
async def root():
    return {
        "message": "Lost & Found API is running",
        "version": "2.0.0",
        "authentication": "JWT Required for all endpoints except this one",
        "endpoints": {
            "submit": "/api/v1/lost-found/submit",
            "all_requests": "/api/v1/lost-found/all",
            "my_requests": "/api/v1/lost-found/my-requests",
            "update_status": "/api/v1/admin/update-status/{id}",
            "setup_create_table": "/api/v1/setup/create-table",
            "generate_test_token": "/api/v1/auth/generate-test-token"
        }
    }

# ===========================================================
# MAIN ENTRY POINT
# ===========================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8052)