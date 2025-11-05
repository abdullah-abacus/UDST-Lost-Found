from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from sqlalchemy import text
import os
from dotenv import load_dotenv
from db_connection import get_db_connection

load_dotenv()

app = FastAPI(
    title="Lost & Found API",
    description="API for Lost and Found Management System",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# ===========================================================
# PYDANTIC MODELS
# ===========================================================
class LostFoundRequest(BaseModel):
    email: str
    description: str
    name: str
    department: str
    rollno: str
    type: RequestType

class LostFoundResponse(BaseModel):
    lnf_id: int
    name: str
    rollno: str
    department: str
    email: str
    description: str
    type: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime]

# ===========================================================
# POST: SUBMIT NEW REQUEST
# ===========================================================
@app.post("/api/v1/lost-found/submit", status_code=201)
async def submit_request(request: LostFoundRequest):
    engine = get_db_connection()
    
    try:
        query = """
            INSERT INTO lost_and_found 
            (email, description, name, department, rollno, type, status, created_at)
            VALUES (:email, :description, :name, :department, :rollno, :type, :status, :created_at)
            RETURNING lnf_id, email, description, name, department, rollno, type, status, created_at;
        """
        values = {
            "email": request.email,
            "description": request.description,
            "name": request.name,
            "department": request.department,
            "rollno": request.rollno,
            "type": request.type.value,  # Convert enum to string
            "status": "pending",
            "created_at": datetime.now()
        }
        
        with engine.connect() as conn:
            result = conn.execute(text(query), values)
            conn.commit()
            return {"message": "Request submitted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit request: {str(e)}")
# ===========================================================
# GET: ALL APPROVED REQUESTS
# ===========================================================
@app.get("/api/v1/lost-found/all")
async def get_all_requests(type: Optional[RequestType] = Query(None, description="Filter by 'lost' or 'found'")):
    engine = get_db_connection()
    
    try:
        table_name = os.getenv("TABLE_NAME", "lost_and_found")
        
        if type:
            query = text(f"""
                SELECT lnf_id, email, description, name, department, rollno, type, status, created_at
                FROM {table_name}
                WHERE status = :status AND type = :type
                ORDER BY created_at DESC;
            """)
            params = {"status": RequestStatus.approved.value, "type": type.value}
        else:
            query = text(f"""
                SELECT lnf_id, email, description, name, department, rollno, type, status, created_at
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
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch requests: {str(e)}")

# ===========================================================
# GET: USER'S OWN REQUESTS (by roll number)
# ===========================================================
@app.get("/api/v1/lost-found/my-requests")
async def get_my_requests(rollno: str = Query(..., description="User's roll number")):
    engine = get_db_connection()
    
    try:
        table_name = os.getenv("TABLE_NAME", "lost_and_found")
        
        query = text(f"""
            SELECT lnf_id, email, description, name, department, rollno, type, status, created_at
            FROM {table_name}
            WHERE rollno = :rollno
            ORDER BY created_at DESC;
        """)
        
        with engine.connect() as conn:
            result = conn.execute(query, {"rollno": rollno})
            results = result.fetchall()
            
            return {
                "success": True,
                "count": len(results),
                "data": [dict(row._mapping) for row in results]
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user requests: {str(e)}")
    

@app.put("/api/v1/admin/update-status/{request_id}")
async def update_request_status(
    request_id: int,
    status: RequestStatus = Query(..., description="New status: 'approved' or 'rejected'")
):
    """
    Update the status of a Lost/Found request.
    Admin can approve or reject pending requests.
    """
    engine = get_db_connection()
    
    try:
        table_name = os.getenv("TABLE_NAME", "lost_and_found")
        
        # First check if request exists
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
                RETURNING lnf_id, email, description, name, department, rollno, type, status, created_at
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
# POST: CREATE TABLE IF NOT EXISTS
# ===========================================================
@app.post("/api/v1/setup/create-table")
async def create_table():
    engine = get_db_connection()
    
    try:
        query = """
        DROP TABLE IF EXISTS lost_and_found;
        CREATE TABLE lost_and_found (
            lnf_id SERIAL PRIMARY KEY,
            email VARCHAR(100) NOT NULL,
            description TEXT NOT NULL,
            name VARCHAR(100) NOT NULL,
            department VARCHAR(100) NOT NULL,
            rollno VARCHAR(50) NOT NULL,
            type VARCHAR(10) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
        with engine.connect() as conn:
            conn.execute(text(query))
            conn.commit()
        return {"message": "Table created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create table: {str(e)}")

# ===========================================================
# HEALTH CHECK
# ===========================================================
@app.get("/")
async def root():
    return {
        "message": "Lost & Found API is running",
        "version": "1.0.0",
        "endpoints": {
            "submit": "/api/v1/lost-found/submit",
            "all_requests": "/api/v1/lost-found/all",
            "my_requests": "/api/v1/lost-found/my-requests",
            "setup_create_table": "/api/v1/setup/create-table"
        }
    }

# ===========================================================
# MAIN ENTRY POINT
# ===========================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8052)
