# Clarity Marketplace - App Submission Requirements

**Version**: 1.0.0  
**Last Updated**: February 2026  
**For**: Agentic App Template v1.0+

---

## 📋 Overview

This document outlines the **requirements and process** for submitting your agentic app built with the Clarity Agentic App Template to the Clarity Marketplace.

### Submission Workflow

```
Developer Builds App → Submit to Clarity → Automated Validation → Manual Review → Approved → Listed in Marketplace
```

**Timeline**: 
- Automated Validation: < 5 minutes
- Manual Review: 1-2 business days
- Total: Usually < 3 business days from submission to marketplace listing

---

## ✅ Pre-Submission Checklist

Before submitting your app, ensure you have completed ALL items below:

### 1. Required Files

- [ ] **app-config.json** - Complete marketplace metadata
- [ ] **README.md** - User-facing documentation
- [ ] **CLAUDE.md** - Developer documentation (optional but recommended)
- [ ] **docker-compose.yml** - With configurable ports
- [ ] **.env.example** - User configuration template
- [ ] **.env.platform.example** - Platform configuration template  
- [ ] **LICENSE** - Open source license file (MIT, Apache 2.0, etc.)
- [ ] **backend/Dockerfile** - Working backend container
- [ ] **frontend/Dockerfile** - Working frontend container

### 2. Required Endpoints

Your backend **MUST** implement these endpoints:

#### Health Check (Required)
```http
GET /health
```
**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-23T10:00:00Z",
  "version": "1.0.0"
}
```

#### Widget Data (Required)
```http
GET /api/widget?size=small|large
```
**Headers**: `X-User-ID: {user_id}`
**Response**: JSON object with widget data

**Small widget response (minimal data)**:
```json
{
  "active_triggers": 5,
  "success_rate": "95%",
  "status": "healthy"
}
```

**Large widget response (detailed data)**:
```json
{
  "active_triggers": 5,
  "total_executions": 42,
  "success_rate": 95.0,
  "recent_executions": [
    {
      "workflow_id": "task-review",
      "status": "completed",
      "started_at": "2026-02-18T10:30:00Z",
      "duration_seconds": 15
    }
  ]
}
```

⚠️ **CRITICAL**: Only TWO widget sizes exist: `small` (300×150px, 2:1 ratio) and `large` (600×400px, 1.5:1 ratio). See [Widget Design Guide](WIDGET_DESIGN_GUIDE.md) for complete specifications.

### 3. Authentication Integration

✅ **MUST** accept `X-User-ID` header  
✅ **MUST** filter all database queries by user_id  
❌ **MUST NOT** allow cross-user data access  
✅ **MAY** also support Bearer token for development

**Example (backend/main.py)**:
```python
def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None)
) -> str:
    if x_user_id:
        return x_user_id
    if authorization:
        return authorization.replace("Bearer ", "").strip()
    raise HTTPException(status_code=401)
```

### 4. Database Multi-Tenancy

✅ **ALL** user data tables MUST have `user_id` column  
✅ **ALL** user data tables MUST have `user_id` index  
✅ **ALL** queries MUST filter by `user_id`  
❌ **NO** global data access without user_id filtering

**Example**:
```python
# ✅ Correct - User-specific query
triggers = db.query(UserTriggerInstance).filter(
    UserTriggerInstance.user_id == user_id
).all()

# ❌ WRONG - Leaks data across users
triggers = db.query(UserTriggerInstance).all()
```

### 5. Port Configuration

✅ Ports MUST be configurable via environment variables  
✅ Use defaults: PostgreSQL=5432, Backend=8000, Frontend=3200  
✅ Support `CONTAINER_PREFIX` for unique container names

**docker-compose.yml example**:
```yaml
services:
  backend:
    container_name: ${CONTAINER_PREFIX:-app}-backend
    ports:
      - "${BACKEND_PORT:-8000}:${BACKEND_INTERNAL_PORT:-8000}"
```

### 6. Security Requirements

❌ **NO** hardcoded secrets, API keys, passwords  
❌ **NO** SQL injection vulnerabilities  
❌ **NO** cross-site scripting (XSS) vulnerabilities  
✅ **YES** encrypted credentials for integrations  
✅ **YES** input validation on all endpoints  
✅ **YES** rate limiting (recommended)  
✅ **YES** CORS properly configured

### 7. Docker Best Practices

✅ Multi-stage builds for smaller images  
✅ Non-root user in containers  
✅ Health checks defined  
✅ Resource limits specified  
✅ .dockerignore files present  
✅ Images build successfully  
✅ All services start within 60 seconds

---

## 📦 Submission Process

### Method 1: GitHub Repository (Recommended)

1. **Push your app to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/your-agentic-app
   git push -u origin main
   ```

2. **Submit via Clarity Platform**
   - Go to [Clarity Developer Dashboard](https://platform.clarity.ai/developer)
   - Click "Submit New App"
   - Select "From GitHub Repository"
   - Enter repository URL
   - Select branch (usually `main`)
   - Click "Submit for Review"

### Method 2: Direct Upload

1. **Package your app**
   ```bash
   # Create submission package
   tar -czf my-app.tar.gz \
     --exclude=node_modules \
     --exclude=.git \
     --exclude=.env \
     --exclude=.env.platform \
     --exclude=postgres_data \
     .
   ```

2. **Submit via Clarity Platform**
   - Go to [Clarity Developer Dashboard](https://platform.clarity.ai/developer)
   - Click "Submit New App"
   - Select "Upload Archive"
   - Upload `my-app.tar.gz`
   - Click "Submit for Review"

---

## 🤖 Automated Validation

Once submitted, your app undergoes automated validation:

### 1. Build Test (⏱️ ~2 minutes)
- ✅ Docker Compose builds successfully
- ✅ All services start within timeout
- ✅ No build errors or warnings

### 2. Endpoint Test (⏱️ ~30 seconds)
- ✅ `/health` returns 200 OK
- ✅ `/health` response is valid JSON
- ✅ `/api/widget` returns 200 OK
- ✅ `/api/widget` accepts X-User-ID header

### 3. Security Scan (⏱️ ~1 minute)
- ✅ No hardcoded secrets in files
- ✅ No SQL injection patterns detected
- ✅ No XSS vulnerabilities found
- ✅ Dependencies have no critical CVEs
- ✅ Docker images pass security scan

### 4. Multi-Tenancy Test (⏱️ ~1 minute)
- ✅ User A cannot access User B's data
- ✅ All database tables have user_id filtering
- ✅ X-User-ID header is respected
- ✅ No data leakage between users

### 5. Configuration Test (⏱️ ~30 seconds)
- ✅ `app-config.json` is valid JSON
- ✅ All required marketplace fields present
- ✅ Ports are configurable via ENV vars
- ✅ `.env.example` has all required variables

**Total Validation Time**: ~5 minutes

---

## 👨‍💼 Manual Review

If automated validation passes, a Clarity team member will:

1. **Review Code Quality**
   - Clean, well-documented code
   - Follows Python/TypeScript best practices
   - No obvious bugs or issues

2. **Test User Experience**
   - App functionality works as described
   - UI is intuitive and responsive
   - Documentation is clear and complete

3. **Verify Marketplace Listing**
   - Screenshots are high quality
   - Description is accurate
   - Features list is correct
   - Pricing model is appropriate

**Timeline**: 1-2 business days

---

## ✅ Approval & Listing

Once approved:

1. **Marketplace Listing Created**
   - App appears in Clarity Marketplace
   - Users can discover and install
   - Reviews and ratings enabled

2. **Developer Dashboard Access**
   - View installation statistics
   - Monitor user reviews
   - Track usage metrics
   - Manage app updates

3. **Revenue Sharing** (if paid app)
   - 70% to developer
   - 30% to Clarity platform
   - Monthly payouts

---

## ❌ Common Rejection Reasons

### Security Issues
- Hardcoded API keys or secrets
- Missing user_id filtering in queries
- SQL injection vulnerabilities
- Insecure credential storage

### Technical Issues
- Docker build failures
- Missing required endpoints
- Health check returns errors
- Ports not configurable

### Documentation Issues
- Missing or incomplete README
- No app-config.json marketplace section
- Unclear installation instructions
- Missing LICENSE file

### Code Quality Issues
- Unhandled exceptions
- Poor error messages
- No input validation
- Commented-out code everywhere

---

## 🔄 Resubmission

If your app is rejected:

1. **Review Feedback**
   - Check email for detailed rejection reasons
   - View specific issues in Developer Dashboard

2. **Fix Issues**
   - Address ALL feedback points
   - Re-test locally

3. **Resubmit**
   - Push fixes to GitHub OR upload new archive
   - Add comment explaining what was fixed
   - Same-day review for resubmissions

---

## 📊 Post-Submission

### Updates

To update your marketplace app:

1. Push changes to GitHub (or upload new version)
2. Increment version in `app-config.json`
3. Click "Submit Update" in Developer Dashboard
4. Automated validation runs again
5. Approval usually within 24 hours

**Backward Compatibility**: 
- Minor updates (1.0.x): Auto-approved if validation passes
- Major updates (x.0.0): Manual review required

### Support

- **Developer Docs**: https://docs.clarity.ai/marketplace
- **Developer Discord**: https://discord.gg/clarity-devs
- **Email Support**: marketplace@clarity.ai
- **Response Time**: < 24 hours

---

## 📝 Marketplace Metadata Reference

### Required Fields (app-config.json)

```json
{
  "clarity_marketplace": {
    "version": "1.0.0",  // Your app version
    "category": "productivity",  // productivity, analytics, communication, etc.
    "tags": ["ai", "automation"],  // 2-5 descriptive tags
    "pricing_model": "free",  // free, paid, freemium
    "developer": {
      "name": "Your Name",
      "email": "you@example.com",
      "support_email": "support@example.com"
    },
    "features": [
      // 3-6 key features as bullet points
    ],
    "api_contract": {
      "health_endpoint": "/health",
      "widget_endpoint": "/api/widget",
      "auth_method": "x-user-id-header"
    }
  }
}
```

### Categories

- **productivity** - Task management, automation, scheduling
- **analytics** - Data analysis, reporting, dashboards
- **communication** - Chat, email, notifications
- **crm** - Customer relationship management
- **content** - Content creation, management, publishing
- **finance** - Accounting, invoicing, payments
- **hr** - Human resources, recruiting, onboarding
- **marketing** - Campaigns, social media, SEO
- **sales** - Pipeline management, proposals, contracts
- **support** - Customer support, helpdesk, ticketing

---

## 🎓 Examples

### Successful Submissions

1. **TaskFlow AI** - AI-powered task management
   - Clean code, comprehensive docs
   - Perfect security score
   - 5-star user reviews
   - [View on Marketplace](https://marketplace.clarity.ai/taskflow-ai)

2. **ContentFlow AI** - Content creation automation
   - Innovative AI features
   - Great UX
   - Active developer support
   - [View on Marketplace](https://marketplace.clarity.ai/contentflow-ai)

---

## 📞 Questions?

- **Email**: marketplace@clarity.ai
- **Discord**: https://discord.gg/clarity-devs
- **Docs**: https://docs.clarity.ai/marketplace/submission
- **Office Hours**: Tuesdays 2-4pm PT

---

**Good luck with your submission! 🚀**
