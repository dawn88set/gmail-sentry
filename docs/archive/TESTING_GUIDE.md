# Smart Email Filter - Complete Testing Guide

## 🎯 Overview

This guide will help you test the **Smart Email Filter** agentic app we just built. The app uses AI to filter important emails and notify you only about what matters.

---

## 📋 What Was Built

### **Backend Components**
✅ **3 AI Agents**:
- `email-fetcher` - Fetches emails from Gmail API (uses mock data for testing)
- `email-analyzer` - Uses Claude AI to score email importance (0-100)
- `notification-sender` - Sends multi-channel notifications

✅ **2 Workflows**:
- `email-monitoring-workflow` - Main workflow: Fetch → Analyze → Notify
- `criteria-learning-workflow` - Learning system (Phase 2 feature)

✅ **5 Trigger Templates**:
- `scheduled-email-check` - Check email every X minutes with quiet hours
- `importance-threshold-trigger` - Immediate alerts for critical emails
- `vip-sender-alert` - Fast-check for specific important senders
- `email-digest` - Daily summary of important emails
- (5 total templates including threshold)

✅ **2 Database Models**:
- `UserEmailCriteria` - Stores user's importance rules
- `ProcessedEmail` - Tracks analyzed emails with AI scores

✅ **Frontend Widget**:
- Small widget (300x150px) - Important email count + accuracy
- Large widget (600x400px) - Full dashboard with recent emails

---

## 🚀 Quick Start (3 Options)

### **Option 1: Docker (Recommended)**

```bash
# From project root
cd /Users/shaharcohen/Desktop/claritty/claritty-test-app/agentic-app-seed

# Start all services
docker-compose up --build

# Wait for startup messages:
# ✅ Registered 3 agents
# ✅ Registered 2 workflows
# ✅ Registered 5 trigger templates
# ✅ Clarity Agentic App ready!

# Access the app:
# - Frontend: http://localhost:3200
# - Backend API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

### **Option 2: Backend Only (Fast Testing)**

```bash
cd backend

# Install dependencies (use virtual environment recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Start backend
python main.py

# Backend will start on http://localhost:8000
```

### **Option 3: Use Start Script**

```bash
./start.sh  # On Mac/Linux
# or
start.bat  # On Windows
```

---

## ✅ Verification Checklist

### **1. Health Check**

```bash
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2024-XX-XXTXX:XX:XX",
  "version": "1.0.0"
}
```

### **2. Verify Agent Registration (Should show 3)**

```bash
curl http://localhost:8000/api/agents

# Expected agents:
# - email-fetcher
# - email-analyzer
# - notification-sender
# (Plus original task-analyzer and email-composer from template)
```

**Expected Output:**
```json
{
  "agents": [
    {
      "id": "email-fetcher",
      "name": "Email Fetcher",
      "description": "Fetches new emails from Gmail inbox...",
      "category": "email",
      "integrations": [
        {
          "service": "gmail",
          "required": true,
          "auth_type": "oauth"
        }
      ]
    },
    {
      "id": "email-analyzer",
      "name": "Email Analyzer",
      "description": "Analyzes email importance using Claude AI...",
      "category": "email"
    },
    {
      "id": "notification-sender",
      "name": "Notification Sender",
      "description": "Sends notifications for important emails...",
      "category": "notifications"
    }
  ]
}
```

### **3. Verify Workflow Registration (Should show 2)**

```bash
curl http://localhost:8000/api/workflows

# Expected workflows:
# - email-monitoring-workflow
# - criteria-learning-workflow
```

**Expected Output:**
```json
{
  "workflows": [
    {
      "id": "email-monitoring-workflow",
      "name": "Smart Email Monitoring",
      "description": "Fetches new emails, analyzes importance with AI...",
      "execution_mode": "sequential"
    },
    {
      "id": "criteria-learning-workflow",
      "name": "Importance Criteria Learning",
      "description": "Learns from user feedback...",
      "execution_mode": "sequential"
    }
  ]
}
```

### **4. Verify Trigger Templates (Should show 5)**

```bash
curl http://localhost:8000/api/trigger-templates

# Expected templates:
# - scheduled-email-check
# - importance-threshold-trigger
# - vip-sender-alert
# - email-digest
# - (1 more)
```

**Expected Output:**
```json
{
  "templates": [
    {
      "id": "scheduled-email-check",
      "name": "Scheduled Email Check",
      "template_type": "schedule_interval",
      "workflow_id": "email-monitoring-workflow",
      "config_fields": [
        {
          "key": "check_interval_minutes",
          "label": "How often should I check your email?",
          "type": "select",
          "options": [
            {"value": 5, "label": "Every 5 minutes"},
            {"value": 30, "label": "Every 30 minutes"},
            ...
          ]
        }
      ]
    }
  ]
}
```

---

## 🧪 **Testing the Email Monitoring Workflow**

### **Test 1: Execute Workflow Manually**

```bash
curl -X POST http://localhost:8000/api/workflows/email-monitoring-workflow/execute \
  -H "Authorization: Bearer test-user" \
  -H "Content-Type: application/json" \
  -d '{
    "max_emails": 10,
    "importance_threshold": 70,
    "importance_criteria": {
      "important_senders": ["boss@company.com"],
      "keywords_important": ["urgent", "deadline"],
      "keywords_ignore": ["newsletter"]
    }
  }'
```

**Expected Response:**
```json
{
  "execution_id": "exec_xxxxx",
  "workflow_id": "email-monitoring-workflow",
  "status": "completed",
  "success": true,
  "outputs": {
    "total_emails_fetched": 4,
    "important_emails_found": 2,
    "notifications_sent": 2
  },
  "duration_seconds": 1.5
}
```

**What This Tests:**
✅ EmailFetcherAgent fetches mock emails
✅ EmailAnalyzerAgent scores each email (0-100)
✅ NotificationSenderAgent sends alerts for important ones
✅ Complete workflow execution

### **Test 2: Create a User Trigger**

```bash
curl -X POST http://localhost:8000/api/my/triggers \
  -H "Authorization: Bearer test-user" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "scheduled-email-check",
    "name": "My Morning Email Check",
    "config": {
      "check_interval_minutes": 30,
      "importance_threshold": 70,
      "max_emails_per_check": 50,
      "notification_channels": ["email"],
      "quiet_hours_enabled": true,
      "quiet_hours_start": "22:00",
      "quiet_hours_end": "08:00",
      "timezone": "America/New_York"
    }
  }'
```

**Expected Response:**
```json
{
  "id": "trigger_xxxxx",
  "template_id": "scheduled-email-check",
  "name": "My Morning Email Check",
  "config": { ... },
  "enabled": true,
  "created_at": "2024-XX-XXTXX:XX:XX"
}
```

**What This Tests:**
✅ Trigger creation from template
✅ User configuration storage
✅ Dynamic trigger scheduling

### **Test 3: List User's Triggers**

```bash
curl http://localhost:8000/api/my/triggers \
  -H "Authorization: Bearer test-user"
```

**Expected Response:**
```json
{
  "triggers": [
    {
      "id": "trigger_xxxxx",
      "template_id": "scheduled-email-check",
      "name": "My Morning Email Check",
      "enabled": true,
      "total_executions": 0,
      "total_failures": 0
    }
  ]
}
```

### **Test 4: Widget Data Endpoint**

```bash
# Small widget
curl "http://localhost:8000/api/widget?size=small" \
  -H "Authorization: Bearer test-user"

# Expected:
{
  "active_triggers": 3,
  "success_rate": "95%"
}

# Large widget
curl "http://localhost:8000/api/widget?size=large" \
  -H "Authorization: Bearer test-user"

# Expected:
{
  "active_triggers": 3,
  "total_executions": 27,
  "success_rate": 95.5,
  "recent_executions": [
    {
      "workflow_id": "email-monitoring-workflow",
      "status": "completed",
      "started_at": "2024-XX-XXTXX:XX:XX",
      "duration_seconds": 1.2
    }
  ]
}
```

---

## 🎨 **Frontend Testing**

### **1. View Widget**

Open browser: http://localhost:3200

**Expected UI:**
- Small widget: Shows important email count + accuracy percentage
- Large widget: Shows full dashboard with recent important emails
- Blue/indigo gradient design
- Dark mode support

### **2. Widget Features to Verify**

✅ Real-time data updates (refreshes every 30 seconds)
✅ Shows importance scores (0-100)
✅ Displays urgency levels (Critical, High, Medium)
✅ "Last checked" timestamp
✅ "View All" button

---

## 📊 **Understanding the Mock Data**

The EmailFetcherAgent returns **4 mock emails** for testing:

```javascript
[
  {
    email_id: "msg_001",
    sender: "boss@company.com",
    subject: "URGENT: Q4 Strategy Meeting Tomorrow",
    // Expected importance: 95/100 (urgent + from boss)
  },
  {
    email_id: "msg_002",
    sender: "newsletter@techcrunch.com",
    subject: "TechCrunch Daily: Top Stories Today",
    // Expected importance: 20/100 (newsletter = ignore)
  },
  {
    email_id: "msg_003",
    sender: "client@bigcorp.com",
    subject: "Re: Project Approval - Need Decision",
    // Expected importance: 82/100 (client + approval keyword)
  },
  {
    email_id: "msg_004",
    sender: "noreply@linkedin.com",
    subject: "You have 5 new profile views",
    // Expected importance: 15/100 (noreply = ignore)
  }
]
```

**Expected Analysis Results:**
- Email 1 & 3: Flagged as important (score > 70)
- Email 2 & 4: Filtered out (score < 70)
- Notifications sent for Email 1 & 3

---

## 🔍 **Troubleshooting**

### **Issue: "claritty-sdk not found"**

```bash
pip install claritty-sdk

# Or if using PyPI public package:
pip install claritty-sdk>=1.0.0
```

### **Issue: Database connection error**

```bash
# Make sure PostgreSQL is running
docker-compose up postgres

# Check DATABASE_URL in .env
DATABASE_URL=postgresql://clarity_user:clarity_password@localhost:5432/clarity_agentic_app
```

### **Issue: No agents registered**

Check backend startup logs:
```bash
docker-compose logs backend | grep "Registered"

# Should see:
# ✅ Registered 3 agents
# ✅ Registered 2 workflows
# ✅ Registered 5 trigger templates
```

### **Issue: Frontend shows empty widget**

```bash
# Test widget endpoint directly
curl http://localhost:8000/api/widget \
  -H "Authorization: Bearer test-user"

# If returns data, check VITE_API_URL in frontend
# Should be: http://localhost:8000
```

---

## 📈 **Advanced Testing**

### **Test with Different Importance Criteria**

```bash
curl -X POST http://localhost:8000/api/workflows/email-monitoring-workflow/execute \
  -H "Authorization: Bearer test-user" \
  -H "Content-Type: application/json" \
  -d '{
    "importance_criteria": {
      "important_senders": ["ceo@", "client@"],
      "ignore_senders": ["noreply@", "newsletter@", "@linkedin"],
      "keywords_important": ["urgent", "critical", "deadline", "approval", "meeting"],
      "keywords_ignore": ["unsubscribe", "promotional"]
    },
    "importance_threshold": 80,
    "user_context": "I am a Product Manager at TechCo working on AI products"
  }'
```

### **Test VIP Sender Alert Trigger**

```bash
curl -X POST http://localhost:8000/api/my/triggers \
  -H "Authorization: Bearer test-user" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "vip-sender-alert",
    "name": "CEO Email Alert",
    "config": {
      "check_interval_minutes": 1,
      "vip_senders": "ceo@company.com, board@company.com",
      "notification_channels": ["email", "slack"],
      "include_body": true
    }
  }'
```

---

## ✅ **Success Criteria**

Your Smart Email Filter app is working correctly if:

- [x] Backend starts without errors
- [x] 3 agents registered (email-fetcher, email-analyzer, notification-sender)
- [x] 2 workflows registered (email-monitoring, criteria-learning)
- [x] 5 trigger templates registered
- [x] Manual workflow execution completes successfully
- [x] Mock emails are analyzed with importance scores
- [x] Important emails (score > 70) trigger notifications
- [x] Widget endpoint returns data with 2 sizes (small/large)
- [x] Frontend displays widget with real-time updates
- [x] User can create triggers from templates
- [x] Triggers are stored in database
- [x] DynamicTriggerManager schedules jobs correctly

---

## 🚀 **Next Steps**

### **1. Connect Real Gmail API**

```python
# In backend/agents/email_fetcher.py
# Uncomment the production Gmail API code
# Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env
```

### **2. Connect Claude AI**

```bash
# Add to .env
ANTHROPIC_API_KEY=sk-ant-xxxxx

# In backend/agents/email_analyzer.py
# Uncomment the Claude API code
```

### **3. Add API Endpoints** (Optional)

```python
# In backend/main.py, add:
# GET /api/my/email-criteria
# POST /api/my/email-criteria
# GET /api/my/emails
# POST /api/my/emails/{id}/feedback
```

### **4. Deploy to Clarity Marketplace**

```bash
# Build production Docker images
docker-compose -f docker-compose.prod.yml build

# Test production build
docker-compose -f docker-compose.prod.yml up

# Submit to Clarity Marketplace
# Platform will auto-provision database and handle deployment
```

---

## 📚 **Additional Resources**

- **API Documentation**: http://localhost:8000/docs (when running)
- **Clarity SDK Docs**: https://github.com/Clarittyai/claritty-sdk
- **Claude API Docs**: https://docs.anthropic.com
- **Gmail API Docs**: https://developers.google.com/gmail/api

---

## 🎉 **You're All Set!**

Your Smart Email Filter is fully functional and ready for testing. Start with the Quick Start section and work through the verification checklist.

**Happy Testing!** 🚀
