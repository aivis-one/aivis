# Endpoint Registry Guide -- probekit-api-sync

## Backend Registry Construction

### Step 1: Find all routers
Read `backend/app/main.py`. Find all `app.include_router()` calls:
```python
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
```
Extract prefix for each router.

### Step 2: Parse router files
For each router module (e.g., `backend/app/modules/auth/router.py`):

Find route decorators:
```python
@router.post("/email/register", response_model=AuthResponse)
async def register(body: EmailRegisterRequest, ...):
```

Extract:
- Method: from decorator (get/post/patch/put/delete)
- Path: decorator argument + router prefix
- Request schema: type hint on `body:` parameter
- Response model: `response_model=` kwarg
- Auth: `Depends(get_current_user)` in parameters

### Step 3: Parse schemas
For each referenced schema, read `modules/*/schemas.py`:
```python
class EmailRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    referral_code: str | None = None
```

Extract field names, types, and whether they have defaults (optional).

### Router discovery patterns
- Main routers: `backend/app/modules/*/router.py`
- Staff routers: `backend/app/modules/*/staff_router.py`
- Nested includes: some modules have `create_router`/`query_router` pattern

---

## Frontend Registry Construction

### Step 1: Find API modules
List all `.ts` files in `mockups/frontend/src/api/` except `client.ts` and `types.ts`.

### Step 2: Parse API calls
For each module (e.g., `src/api/auth.ts`):
```typescript
login(data: LoginRequest): Promise<AuthResponse> {
  return api.post<AuthResponse>('/api/v1/auth/email/login', data, { skipAuth: true })
}
```

Extract:
- Method: api.get/post/patch/put/delete
- Path: first string argument
- Request type: second argument type (or FormData for uploads)
- Response type: generic type parameter `<T>`
- skipAuth: presence of `{ skipAuth: true }`

### Step 3: Parse types
Read `src/api/types.ts`:
```typescript
export interface LoginRequest {
  email: string
  password: string
}
```

Extract interface names, field names, and field types.

### Special cases
- `apiUpload<T>(path, formData)`: multipart upload, no Content-Type header
- Paginated responses: `PaginatedResponse<T>` wrapper
