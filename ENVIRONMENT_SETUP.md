# Environment Setup Guide

## ✅ What's Already Installed

### System
- **OS:** macOS (ARM64)
- **Python:** 3.14.6
- **Node:** v24.14.1
- **npm:** 11.11.0
- **Git:** ✅ (active on dev-slot branch)

### Python Packages (Backend)
```
✅ fastapi          0.138.1
✅ uvicorn          0.49.0
✅ sqlalchemy       2.0.36
✅ psycopg2-binary  2.9.10
✅ pydantic         2.10.6
✅ requests         2.31.0
✅ azure-*          (identity, storage-blob)
```

### Frontend
```
✅ node_modules/    (installed, 975 packages)
✅ package.json     (exists)
✅ frontend/src/    (all source files)
```

### Project Files
```
✅ app/main.py      (backend entry point)
✅ requirements.txt (all dependencies listed)
✅ frontend/src/    (all React components)
✅ All documentation (FEATURES_EXPLAINED.md, etc.)
```

---

## 🚀 Quick Start - Frontend

```bash
cd frontend
npm start
# Opens http://localhost:3000
```

## 🚀 Quick Start - Backend

```bash
# Activate virtual environment (if using one)
source venv/bin/activate

# Install dependencies (if needed)
python3 -m pip install -r requirements.txt

# Run backend
python3 -m uvicorn app.main:app --reload
# Or
uvicorn app.main:app --reload
# Opens http://localhost:8000/docs (API docs)
```

---

## 🔧 Potential Issues & Solutions

### Issue 1: "No module named uvicorn"
**Cause:** Python PATH issue or venv not activated

**Solution:**
```bash
# Check which python is being used
which python3
python3 --version

# Make sure uvicorn is installed
python3 -m pip list | grep uvicorn

# If missing, install it
python3 -m pip install uvicorn

# Try running with full path
python3 -m uvicorn app.main:app --reload
```

### Issue 2: Frontend won't start
**Cause:** node_modules missing or outdated

**Solution:**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm start
```

### Issue 3: "Cannot find module '@tanstack/react-query'"
**Cause:** node_modules not fully installed

**Solution:**
```bash
cd frontend
npm install
# or
npm ci  # Clean install
```

### Issue 4: Port 3000 already in use (frontend)
**Solution:**
```bash
# Use different port
PORT=3001 npm start
# or kill process on 3000
lsof -i :3000
kill -9 <PID>
```

### Issue 5: Port 8000 already in use (backend)
**Solution:**
```bash
# Use different port
uvicorn app.main:app --reload --port 8001
```

---

## 📋 Pre-Development Checklist

- [ ] Python 3.13+ installed (`python3 --version`)
- [ ] Node 20+ installed (`node --version`)
- [ ] npm 10+ installed (`npm --version`)
- [ ] Git installed (`git --version`)
- [ ] On dev-slot branch (`git branch`)
- [ ] Backend requirements installed (`python3 -m pip list | grep uvicorn`)
- [ ] Frontend dependencies installed (`cd frontend && ls node_modules`)
- [ ] .env file configured (if needed for backend)
- [ ] Database configured (if needed for backend)

---

## 📚 Documentation Reference

After setup, read in this order:

1. **QUICK_REFERENCE.md** (5 min) - Feature overview
2. **FEATURES_EXPLAINED.md** (30 min) - Deep learning
3. **TESTING_GUIDE.md** (start testing) - Step-by-step
4. **TEST_CHECKLIST.md** (while testing) - Detailed scenarios

---

## 🎯 Development Workflow

```bash
# Terminal 1: Backend
python3 -m uvicorn app.main:app --reload

# Terminal 2: Frontend
cd frontend
npm start

# Terminal 3: Git (optional)
git status
git branch -vv

# Browser
# Frontend: http://localhost:3000
# Backend API Docs: http://localhost:8000/docs
```

---

## 🔗 Important Endpoints

### Frontend (React)
- Main app: http://localhost:3000
- OptimizationHub: http://localhost:3000/optimization
- Actions tab: http://localhost:3000/optimization (then click "Actions")

### Backend (FastAPI)
- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

---

## 🐛 Troubleshooting Quick Links

| Problem | Solution |
|---------|----------|
| Python module not found | `python3 -m pip install -r requirements.txt` |
| Node module not found | `cd frontend && npm install` |
| Port already in use | Use different port or kill process |
| Git conflicts | `git status` and resolve conflicts |
| CSS not loading | `cd frontend && npm run build` |
| API not responding | Check backend running on 8000 |

---

## ✨ Next Steps

1. **Verify setup:** Run quick start commands above
2. **Test frontend:** Navigate to http://localhost:3000/optimization
3. **Test backend:** Open http://localhost:8000/docs
4. **Read docs:** Start with QUICK_REFERENCE.md
5. **Run tests:** Follow TESTING_GUIDE.md

---

**Everything should be ready to go!** 🚀

If you hit issues, check Troubleshooting section above.

