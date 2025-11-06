# jwt_wrapper.py for FastAPI

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
import os
from datetime import datetime, timezone
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from functools import wraps

SECRET_KEY = os.getenv('SECRET_KEY')
TOKEN_CUTOFF_DATE = datetime(2026, 11, 12, tzinfo=timezone.utc)
CLIENT_CREDENTIALS = {
    'client_id': os.getenv('STATIC_CLIENT_ID'),
    'client_secret': os.getenv('STATIC_CLIENT_SECRET')
}

security = HTTPBearer()

# ✅ Generate token using both client_id and client_secret
def generate_token(client_id: str, client_secret: str, user_data: dict = None):
    """
    Generate JWT token with client credentials and optional user data
    """
    print("Generating token with client_id:", client_id)
    print("Generating token with client_secret:", client_secret)

    if datetime.now(tz=timezone.utc) >= TOKEN_CUTOFF_DATE:
        raise Exception("Your access to API Assistant has expired. Please contact Abacus to renew your subscription.")

    # 🔸 Verify provided credentials against env values
    if client_id != CLIENT_CREDENTIALS["client_id"] or client_secret != CLIENT_CREDENTIALS["client_secret"]:
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    # 🔹 Include both client_id and client_secret in payload
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
    }
    
    # Add user data if provided
    if user_data:
        payload.update(user_data)

    # Static deterministic token (no exp)
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def token_required(func):
    @wraps(func)
    async def wrapper(*args, request: Request = None, **kwargs):
        # ✅ Find the request object
        if not request:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

        if not request:
            raise HTTPException(status_code=500, detail="Request object not found")

        # ✅ Check Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            raise HTTPException(status_code=401, detail="Authorization header is missing")

        try:
            token = auth_header.split(" ")[1]
            print("Incoming Token:", token)

            # Decode the token
            decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            print("Decoded Token:", decoded_token)

            # ✅ Check client_id and client_secret in token (FIXED: using AND not OR)
            if (
                decoded_token.get("client_id") and 
                decoded_token.get("client_secret") and
                decoded_token.get("client_id").lower() == CLIENT_CREDENTIALS["client_id"].lower() and
                decoded_token.get("client_secret").lower() == CLIENT_CREDENTIALS["client_secret"].lower()
            ):
                print("✅ Token is valid.")
            else:
                print("❌ Token mismatch")
                print(f"Expected client_id: {CLIENT_CREDENTIALS['client_id']}, Got: {decoded_token.get('client_id')}")
                print(f"Expected client_secret: {CLIENT_CREDENTIALS['client_secret']}, Got: {decoded_token.get('client_secret')}")
                raise HTTPException(status_code=401, detail="Token mismatch. Unauthorized access.")
            
            # ✅ Attach decoded token to request state for later use
            request.state.decoded_token = decoded_token
            request.state.client_id = decoded_token.get("client_id")
            
            # Store user data if present
            if "user_id" in decoded_token:
                request.state.user_id = decoded_token.get("user_id")
                request.state.user_role = decoded_token.get("user_role")
                request.state.user_name = decoded_token.get("name")
                request.state.user_email = decoded_token.get("email")
                request.state.user_department = decoded_token.get("department")

        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except JWTError as e:
            print(f"JWT Error: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid or malformed token: {str(e)}")
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")

        # ✅ Pass request properly to the wrapped route
        return await func(request=request, *args, **kwargs)

    return wrapper


# ✅ Dependency for alternate usage in routes
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

        if (
            decoded_token.get("client_id") != CLIENT_CREDENTIALS["client_id"] or
            decoded_token.get("client_secret") != CLIENT_CREDENTIALS["client_secret"]
        ):
            raise HTTPException(status_code=401, detail="Token mismatch. Unauthorized access.")

        return decoded_token

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or malformed token")