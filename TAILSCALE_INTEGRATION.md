# Tailscale Backend Integration Documentation

## Overview

This document details the amendments made to enable the MedJournee PWA (hosted on Render) to communicate with the FastAPI backend hosted on a Tailscale private network at IP `100.82.173.110`.

---

## Architecture Context

### Before Changes
```
User Browser
    ↓
Render Static Site (PWA) - Served via HTTPS
    ↓ (API calls to window.location.origin)
[X] FAIL - Backend not on same origin
```

### After Changes
```
User Browser (with Tailscale client)
    ↓
Render Static Site (PWA) - Served via HTTPS
    ↓ (API calls to http://100.82.173.110:8000)
Tailscale Network
    ↓
FastAPI Backend at 100.82.173.110:8000
```

---

## Amendments Made

### 1. CORS Configuration (`main.py`)

**Location:** Lines 66-72

**Original Code:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Amended Code:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://medjournee.onrender.com",  # Render PWA frontend (UPDATE THIS)
        "http://localhost:8000",             # Local development
        "http://localhost:3000",             # Local development alternative
        "http://localhost:8080",             # Local development alternative
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Reasoning:**
- Browser security requires explicit CORS configuration when frontend and backend are on different origins
- The wildcard `"*"` is replaced with specific allowed origins for security
- **CRITICAL:** You must update `"https://medjournee.onrender.com"` to your actual Render domain
- Localhost entries preserved for development purposes

**Logic:**
- When the browser makes a request from `https://your-app.onrender.com` to `http://100.82.173.110:8000`, it's a cross-origin request
- The browser sends a preflight OPTIONS request
- FastAPI must respond with `Access-Control-Allow-Origin: https://your-app.onrender.com`
- Without this, the browser blocks the request with a CORS error

---

### 2. Frontend API Base URL (`static/mobile.html`)

**Location:** Line 398

**Original Code:**
```javascript
const API_BASE = window.location.origin;
```

**Amended Code:**
```javascript
const API_BASE = 'http://100.82.173.110:8000';  // Tailscale backend IP
```

**Reasoning:**
- `window.location.origin` returns the current page's origin (e.g., `https://your-app.onrender.com`)
- Since backend and frontend are now separate, we must explicitly point to the backend
- The Tailscale IP `100.82.173.110` is only accessible within the Tailscale network

**Logic:**
- All API calls now go directly to the Tailscale IP
- Example: `${API_BASE}/appointments/month/...` becomes `http://100.82.173.110:8000/appointments/month/...`

---

### 3. Frontend API Base URL (`static/record.html`)

**Location:** Line 434

**Original Code:**
```javascript
const API_BASE = window.location.origin;
```

**Amended Code:**
```javascript
const API_BASE = 'http://100.82.173.110:8000';  // Tailscale backend IP
```

**Reasoning:**
- Same as mobile.html - the recording interface needs to communicate with the backend
- This page handles real-time transcription and session finalization

**Logic:**
- Critical endpoints used: `/realtime/instant-transcribe/`, `/realtime/finalize-session/`
- These must reach the backend through Tailscale

---

### 4. Frontend API Base URL (`static/appointment.html`)

**Location:** Line 223

**Original Code:**
```javascript
const API_BASE = window.location.origin;
```

**Amended Code:**
```javascript
const API_BASE = 'http://100.82.173.110:8000';  // Tailscale backend IP
```

**Reasoning:**
- Appointment management interface
- Uses endpoints like `/appointments/create`, `/talking-points/create`

**Logic:**
- Ensures appointment CRUD operations reach the backend
- Talking points functionality preserved

---

### 5. Frontend API Base URL (`static/entry.html`)

**Location:** Line 573

**Original Code:**
```javascript
const API_BASE = window.location.origin;
```

**Amended Code:**
```javascript
const API_BASE = 'http://100.82.173.110:8000';  // Tailscale backend IP
```

**Reasoning:**
- Journal entry viewing interface
- Uses endpoints like `/live-session/get-journal/`, `/appointments/link/`

**Logic:**
- Journal entry retrieval and appointment linking must work across Tailscale

---

## Tailscale Serve Explained

### What is Tailscale Serve?

`tailscale serve` is a Tailscale feature that provides **HTTPS endpoints** for services running on your Tailscale devices. It solves the "mixed content" problem when your frontend (HTTPS) needs to talk to your backend (HTTP).

### Why You Need It

| Without Serve | With Serve |
|---------------|------------|
| Backend at `http://100.82.173.110:8000` | Backend at `https://your-desktop.tailnet-name.ts.net` |
| HTTP protocol | HTTPS protocol |
| ❌ Blocked by browsers (mixed content) | ✅ Works in all browsers |
| Direct IP access | MagicDNS hostname |

### How It Works

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   User Browser  │ ──────▶ │  Tailscale Serve │ ──────▶ │  FastAPI App    │
│   (HTTPS PWA)   │         │  (Reverse Proxy) │         │  (localhost:8000)│
└─────────────────┘         └──────────────────┘         └─────────────────┘
         │                           │                           │
         │    https://terra.         │      http://              │
         │    tail8736aa.ts.net      │      localhost:8000       │
         │                           │                           │
         └───────────────────────────┘                           │
              Tailscale provides                                  │
              TLS certificate                                     │
              (free & automatic)                                  │
```

### The Command

```bash
# On your Tailscale machine (your desktop)
tailscale serve --https=443 localhost:8000
```

**What this does:**
1. Creates an HTTPS endpoint at `https://your-machine.tailnet-name.ts.net`
2. Obtains a free TLS certificate automatically (via Let's Encrypt)
3. Proxies all requests to `localhost:8000` (your FastAPI app)
4. Only accessible to devices on your Tailscale network

### Getting Your Serve URL

After running the command, get your URL:

```bash
tailscale serve status
```

Output example:
```
https://terra.tail8736aa.ts.net (serve)
|-- / proxy http://127.0.0.1:8000
```

Use this URL in your frontend's `API_BASE`.

### Serve vs Funnel

| Feature | `tailscale serve` | `tailscale funnel` |
|---------|-------------------|-------------------|
| **Who can access** | Only your Tailnet members | **Public internet** |
| **Authentication** | Tailscale login required | None |
| **Use case** | Private internal tools | Public services |
| **Security** | Private by default | Public by default |
| **Cost** | Free | Free |
| **You want this?** | ✅ **YES** | ❌ No |

### Common Serve Commands

```bash
# Start serving
tailscale serve --https=443 localhost:8000

# Check status
tailscale serve status

# Stop serving
tailscale serve --https=443 off

# Serve on different port
tailscale serve --https=8443 localhost:8000
```

### Troubleshooting Serve

**Problem: "certificates not enabled"**

**Fix:** Enable HTTPS in Tailscale admin console:
1. Go to https://login.tailscale.com/admin/settings/features
2. Turn on **HTTPS Certificates**
3. Wait 1-2 minutes
4. Try `tailscale serve` again

**Problem: "address already in use"**

**Fix:** Port 443 is taken. Use a different port:
```bash
tailscale serve --https=8443 localhost:8000
# Then access via https://your-machine.tailnet-name.ts.net:8443
```

**Problem: Serve URL not working**

**Checks:**
1. Is your FastAPI app running on `localhost:8000`?
2. Is Tailscale connected? (`tailscale status`)
3. Try accessing from same machine: `curl https://your-machine.tailnet-name.ts.net/test`

---

## Critical Configuration Steps (Required)

### Step 1: Update Render Domain in CORS

**Action Required:** Edit `main.py` line 68

Replace:
```python
"https://medjournee.onrender.com",  # Render PWA frontend (UPDATE THIS)
```

With your actual Render domain:
```python
"https://your-actual-app-name.onrender.com",
```

**How to find your Render domain:**
1. Go to https://dashboard.render.com
2. Select your static site
3. Copy the URL (e.g., `https://medjournee-abc123.onrender.com`)

---

### Step 2: Ensure Tailscale Connectivity

**Prerequisites:**

1. **Backend machine must have Tailscale running:**
   ```bash
   sudo tailscale up
   ```

2. **User devices must have Tailscale:**
   - Install Tailscale app on phone/computer
   - Login with same Tailnet account
   - Verify connection: `tailscale status` should show `100.82.173.110`

3. **Backend FastAPI must be accessible:**
   ```bash
   # On backend machine
   uvicorn main:app --host 0.0.0.0 --port 8000
   
   # Verify it's listening on all interfaces
   netstat -tlnp | grep 8000
   # Should show: 0.0.0.0:8000
   ```

---

## Known Limitations & Security Considerations

### 1. Mixed Content Warning (HTTPS → HTTP)

**Issue:**
- Render serves the PWA via HTTPS
- Tailscale IP uses HTTP (`http://100.82.173.110:8000`)
- Modern browsers block "mixed content" (HTTPS page calling HTTP API)

**Impact:**
- Browser console error: "Mixed Content: The page at 'https://...' was loaded over HTTPS, but requested an insecure XMLHttpRequest endpoint 'http://100.82.173.110:8000/...'"
- API calls will fail

**Solutions:**

#### Option A: Enable Tailscale HTTPS (Recommended)
```bash
# On your Tailscale machine
tailscale serve --https=443 localhost:8000

# This creates: https://your-machine.tailnet-name.ts.net
# Update API_BASE in HTML files to use this HTTPS URL
```

#### Option B: User Browses via HTTP (Not Recommended)
- Access Render app via HTTP instead of HTTPS
- Render may not support this for static sites
- Loses security benefits

#### Option C: Use Tailscale Funnel (Public HTTPS)
```bash
tailscale funnel --https=443 localhost:8000
# Creates public HTTPS URL, but bypasses Tailscale ACLs
```

---

### 2. CORS Pre-flight Requests

**Issue:**
- Every API call triggers an OPTIONS pre-flight request
- Slight latency increase (negligible for this use case)

**Mitigation:**
- Already handled by FastAPI CORSMiddleware
- No action required

---

### 3. Authentication Not Implemented

**Current State:**
- No API authentication in place
- Anyone with Tailscale access can hit the backend

**Recommendation:**
- Implement API key authentication
- Or use Tailscale ACLs to restrict which devices can access port 8000

**Tailscale ACL Example:**
```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["group:medjournee-users"],
      "dst": ["100.82.173.110:8000"]
    }
  ]
}
```

---

## Testing the Integration

### Test 1: Backend Accessibility

From a device with Tailscale:
```bash
curl http://100.82.173.110:8000/test
```

Expected response:
```json
{"message": "App is alive", "status": "healthy"}
```

### Test 2: CORS Headers

From a device with Tailscale:
```bash
curl -X OPTIONS -H "Origin: https://your-app.onrender.com" \
  -H "Access-Control-Request-Method: GET" \
  -I http://100.82.173.110:8000/test
```

Expected headers:
```
Access-Control-Allow-Origin: https://your-app.onrender.com
Access-Control-Allow-Methods: GET, POST, OPTIONS
```

### Test 3: Full Flow via Browser

1. Open browser DevTools (F12)
2. Navigate to your Render PWA URL
3. Try to load appointments or journal entries
4. Check Network tab:
   - Requests should go to `100.82.173.110:8000`
   - Status should be 200 (not blocked by CORS)

---

## Rollback Instructions

If you need to revert these changes:

### Revert CORS (`main.py`)
```python
allow_origins=["*"],
```

### Revert Frontend (`static/*.html`)
```javascript
const API_BASE = window.location.origin;
```

---

## Troubleshooting Guide

### Problem: "CORS error" in browser console

**Diagnosis:**
- Check that your Render domain is in `allow_origins` list in `main.py`
- Verify domain format includes `https://` and no trailing slash

**Fix:**
```python
# Wrong
"medjournee.onrender.com"
"https://medjournee.onrender.com/"

# Correct
"https://medjournee.onrender.com"
```

---

### ⚠️ CRITICAL: Trailing Slash Gotcha

**This is the #1 mistake when configuring CORS.**

Browsers send the `Origin` header WITHOUT a trailing slash:
```
Origin: https://medjournee-backend.onrender.com
```

But if your CORS config INCLUDES the trailing slash:
```python
allow_origins=["https://medjournee-backend.onrender.com/"]  # ❌ WRONG
```

The browser sees these as **different origins** and blocks the request.

**Symptoms:**
- Everything looks correct
- Backend is running
- Tailscale is connected
- Still get CORS errors

**The Fix:**
```python
# ❌ WRONG - trailing slash
"https://medjournee-backend.onrender.com/"

# ✅ CORRECT - no trailing slash
"https://medjournee-backend.onrender.com"
```

**Always remove the trailing slash from CORS origins.**

---

### Problem: "Failed to fetch" or "Network Error"

**Diagnosis:**
- Tailscale not connected on user device
- Backend not running on 100.82.173.110:8000
- Firewall blocking port 8000

**Checks:**
```bash
# From user device
ping 100.82.173.110
curl http://100.82.173.110:8000/test

# From backend machine
sudo ufw allow 8000  # If using UFW
sudo iptables -L | grep 8000
```

---

### Problem: "Mixed Content" error

**Diagnosis:**
- Browser blocking HTTP calls from HTTPS page

**Fix:**
See "Mixed Content Warning" section above - enable Tailscale HTTPS.

---

## Summary of Changes

| File | Line | Change Type | Description |
|------|------|-------------|-------------|
| `main.py` | 66-72 | CORS origins | Restricted to specific domains including Render |
| `static/mobile.html` | 398 | API_BASE | Changed from `window.location.origin` to Tailscale IP |
| `static/record.html` | 434 | API_BASE | Changed from `window.location.origin` to Tailscale IP |
| `static/appointment.html` | 223 | API_BASE | Changed from `window.location.origin` to Tailscale IP |
| `static/entry.html` | 573 | API_BASE | Changed from `window.location.origin` to Tailscale IP |

**Total files modified:** 5
**Total lines changed:** 5 (one per file)

---

## Next Steps Checklist

- [ ] Update `main.py` with actual Render domain
- [ ] Deploy updated backend to 100.82.173.110
- [ ] Redeploy PWA to Render (git push)
- [ ] Test Tailscale connectivity from user device
- [ ] Resolve HTTPS/HTTP mixed content (enable Tailscale HTTPS)
- [ ] Verify all PWA functions work (record, transcribe, save journal)
- [ ] (Optional) Implement API authentication
- [ ] (Optional) Configure Tailscale ACLs for port 8000

---

## Contact & Support

For issues with:
- **Tailscale connectivity:** https://tailscale.com/kb/
- **Render deployment:** https://render.com/docs
- **FastAPI CORS:** https://fastapi.tiangolo.com/tutorial/cors/

---

*Document generated for MedJournee Tailscale Integration*
*Backend IP: 100.82.173.110*
*Date: 2026-03-02*
