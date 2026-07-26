---
name: scanner-patterns
description: "v1.0.0 | Regex patterns and semantic mapping for backend/frontend/spec scanning"
---

# Scanner Patterns

Exact extraction patterns for all three data sources.

---

## 1. Backend Router Scanning

**Files**: `backend/app/modules/*/router.py`, `backend/app/main.py`

### Router prefix
```
APIRouter\(prefix="([^"]+)"
```
Example: `APIRouter(prefix="/api/v1/auth")` -> `/api/v1/auth`

### Route decorator
```
@router\.(get|post|patch|put|delete)\(\s*"([^"]+)"
```
Example: `@router.post("/email/register")` -> method=POST, path=/email/register

### Full endpoint path
```
full_path = router_prefix + route_path
```
Example: `/api/v1/auth` + `/email/register` -> `POST /api/v1/auth/email/register`

### Response model
```
response_model=(\w+)
```

### Status code
```
status_code=(\d+)
```

### Dependencies
```
Depends\((\w+)\)
```
Key dependencies: `get_current_user`, `get_current_staff`, `get_db_session`, `get_db_reader`

### System endpoints (main.py)
```
@app\.(get|post)\("([^"]+)"
```

### Router registration (main.py)
```
app\.include_router\((\w+)\.router
```

---

## 2. Backend Model Scanning

**Files**: `backend/app/modules/*/models.py`, `backend/app/core/audit.py`

### Model class
```
class\s+(\w+)\([^)]*Base[^)]*\):
```

### Table name
```
__tablename__\s*=\s*["']([^"']+)["']
```

### Column definition
```
(\w+):\s*Mapped\[([^\]]+)\]\s*=\s*mapped_column\(([^)]*)\)
```
Groups: column_name, python_type, column_args

### JSONB column (special case)
```
(\w+):\s*Mapped\[dict[^]]*\]\s*=\s*mapped_column\(JSONB
```

### Foreign key
```
ForeignKey\(["']([^"']+)["']\)
```

### Enum class
```
class\s+(\w+)\(.*(?:str,\s*)?[Ee]num\):
```

### Index
```
Index\(["']([^"']+)["']
```

---

## 3. Backend Service Scanning

**Files**: `backend/app/modules/*/service.py`

### Function definition
```
async\s+def\s+(\w+)\(
```

### Model imports
```
from\s+app\.modules\.(\w+)\.models\s+import\s+(.+)
```
Groups: module_name, imported_names

### Cross-service imports
```
from\s+app\.modules\.(\w+)\.service\s+import
```

---

## 4. Frontend Screen Scanning

**Files**: `mockups/*/mockup.html` (exclude `!site/`, `project-map/`, `css/`, `js/`)

### Role detection
Directory name mapping:
| Directory | Role |
|-----------|------|
| `auth-flow` | auth (all roles) |
| `investor-shell` | investor |
| `agent-shell` | agent |
| `company-shell` | company |
| `staff-shell` | staff |

### Screen ID
```
id="(screen-[\w-]+)"
```

### Navigation actions (no API needed)
```
navigateTo\(['"]([^'"]+)['"]\)
switchTab\(['"]([^'"]+)['"]
```

### Endpoint markers (API needed)
```
showToast\(['"]([^'"]*endpoint[^'"]*)['"]\)
```
Toast text containing "endpoint" = feature needs backend implementation.

### Data entity CSS classes
Look for these class patterns within each screen's `<div>`:

| CSS Class | Entity Type | Typical API |
|-----------|-------------|-------------|
| `.tx-item` | Transaction | GET /transactions |
| `.stat-card` | Dashboard stat | GET /dashboard |
| `.product-item`, `.product-card` | Product | GET /products |
| `.portfolio-item` | Portfolio holding | GET /portfolio |
| `.news-item` | News/post | GET /posts |
| `.doc-item` | Document | GET /documents |
| `.comm-item` | Commission | GET /commissions |
| `.agent-item` | Agent ranking | GET /leaderboard |
| `.user-item` | User list | GET /staff/users |
| `.balance-card` | Balance | GET /balance |
| `.setting-row` | Settings | GET/PATCH /settings |
| `.form-group` | Form submission | POST/PATCH endpoint |
| `.ref-card` | Referral link | GET /referrals |

### Form submission detection
```
<form|<button[^>]*class="btn btn-primary"[^>]*onclick
```
Forms with primary buttons indicate write operations (POST/PUT/PATCH).

---

## 5. Spec Document Scanning

**File**: `CBSHOME-Backend.md`

### Sprint header
```
###\s*(?:✅|☑)?\s*Sprint\s+(\d+\.\d+):\s*(.+)
```
Groups: sprint_id, sprint_name
Checkmark prefix = sprint completed.

### Endpoint declaration
```
[`*]*(GET|POST|PATCH|PUT|DELETE)\s+(/api/v1/\S+)[`*]*
```
May be inside backticks or bold markers.

### Task checkbox
```
-\s*\[(x| )\]\s*(.+)
```
`[x]` = done, `[ ]` = pending

### Phase header
```
##\s*(?:Phase)\s+(\d+)
```

---

## 6. Semantic Screen-to-Endpoint Mapping

This table maps each mockup screen to its required API endpoints.
Claude uses this during cross-reference (scan step 6) to determine what each screen needs.

### auth-flow screens
| Screen | Required Endpoints |
|--------|-------------------|
| screen-login | `POST /api/v1/auth/email/login`, `POST /api/v1/auth/telegram` |
| screen-register | `POST /api/v1/auth/email/register` |
| screen-verify | `POST /api/v1/auth/verify-email` |
| screen-profile | `GET /api/v1/users/me`, `PATCH /api/v1/users/me` |
| screen-role | `PATCH /api/v1/users/me` (role selection) |
| screen-kyc | `GET /api/v1/kyc/status`, `POST /api/v1/kyc/submit` |
| screen-docs | `GET /api/v1/documents/onboarding`, `POST /api/v1/documents/{id}/sign` |

### investor-shell screens
| Screen | Required Endpoints |
|--------|-------------------|
| screen-dashboard | `GET /api/v1/investor/dashboard`, `GET /api/v1/portfolio/summary`, `GET /api/v1/balance/me`, `GET /api/v1/transactions?limit=3`, `GET /api/v1/posts?limit=2` |
| screen-portfolio | `GET /api/v1/portfolio/holdings` |
| screen-market | `GET /api/v1/products?status=active` |
| screen-product | `GET /api/v1/products/{id}` |
| screen-purchase | `POST /api/v1/purchases`, `GET /api/v1/balance/me` |
| screen-installment | `GET /api/v1/installment-plans/{productId}`, `POST /api/v1/installment-purchases` |
| screen-balance | `GET /api/v1/balance/me`, `GET /api/v1/transactions` |
| screen-docs | `GET /api/v1/documents/me` |
| screen-settings | `GET /api/v1/users/me`, `PATCH /api/v1/users/me` |

### agent-shell screens
| Screen | Required Endpoints |
|--------|-------------------|
| screen-dashboard | `GET /api/v1/agent/dashboard`, `GET /api/v1/agent/commissions?limit=2` |
| screen-hub | `GET /api/v1/agent/hub`, `GET /api/v1/agent/earnings-breakdown` |
| screen-referrals | `GET /api/v1/agent/referrals`, `POST /api/v1/agent/referrals` |
| screen-commissions | `GET /api/v1/agent/commissions` |
| screen-leaderboard | `GET /api/v1/leaderboard/agents` |
| screen-passive | `GET /api/v1/agent/passive-balance`, `POST /api/v1/agent/withdrawals` |
| screen-settings | `GET /api/v1/users/me`, `PATCH /api/v1/users/me` |

### company-shell screens
| Screen | Required Endpoints |
|--------|-------------------|
| screen-dashboard | `GET /api/v1/company/dashboard`, `GET /api/v1/company/transactions?limit=3` |
| screen-products | `GET /api/v1/company/products` |
| screen-product-edit | `GET /api/v1/company/products/{id}`, `PUT /api/v1/company/products/{id}` |
| screen-analytics | `GET /api/v1/company/analytics`, `GET /api/v1/company/analytics/top-agents` |
| screen-settings | `GET /api/v1/company/settings`, `PATCH /api/v1/company/settings` |

### staff-shell screens
| Screen | Required Endpoints |
|--------|-------------------|
| screen-dashboard | `GET /api/v1/staff/dashboard` |
| screen-users | `GET /api/v1/staff/users` |
| screen-kyc | `GET /api/v1/staff/kyc/queue`, `POST /api/v1/staff/kyc/{id}/approve`, `POST /api/v1/staff/kyc/{id}/reject` |
| screen-payments | `GET /api/v1/staff/payments/pending`, `POST /api/v1/staff/payments/{id}/confirm`, `POST /api/v1/staff/payments/{id}/reject` |
| screen-more | `GET /api/v1/staff/settings` |
| screen-agent-apps | `GET /api/v1/staff/agent-applications`, `POST /api/v1/staff/agent-applications/{id}/approve`, `POST /api/v1/staff/agent-applications/{id}/reject` |
| screen-avatar | `POST /api/v1/staff/avatar-sessions`, `DELETE /api/v1/staff/avatar-sessions/{id}` |

---

## 7. Business Flow Definitions

Named user journeys for flow scoring:

| Flow ID | Name | Steps (screens) |
|---------|------|-----------------|
| `inv.onboard` | Investor Onboarding | login -> register -> verify -> profile -> role -> kyc -> docs -> dashboard |
| `inv.purchase` | Investor Purchase | dashboard -> market -> product -> purchase -> (success) -> portfolio |
| `inv.installment` | Investor Installment | product -> installment -> (success) -> balance |
| `inv.deposit` | Investor Deposit | balance -> (deposit crypto) -> balance |
| `agent.onboard` | Agent Onboarding | login -> register -> verify -> profile -> role(agent) -> kyc -> docs -> dashboard |
| `agent.earn` | Agent Earnings Flow | dashboard -> hub -> commissions -> passive -> (withdraw) |
| `agent.refer` | Agent Referral | hub -> referrals -> (create link) -> (share) |
| `comp.manage` | Company Product Mgmt | dashboard -> products -> product-edit -> (save) -> products |
| `comp.analytics` | Company Analytics | dashboard -> analytics -> (top agents) |
| `staff.kyc` | Staff KYC Review | dashboard -> kyc -> (approve/reject) |
| `staff.payment` | Staff Payment Review | dashboard -> payments -> (confirm/reject) |
| `staff.avatar` | Staff Avatar Mode | more -> avatar -> (select user) -> (impersonate) |

---

*scanner-patterns v1.0.0*
