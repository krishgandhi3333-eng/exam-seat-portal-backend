Here's ALL your code! Copy everything you need:
Action: file_editor view /app/backend/server.py
Observation: [Showing lines 1-407 of 407 total] /app/backend/server.py:
1|from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File
2|from fastapi.responses import JSONResponse
3|from dotenv import load_dotenv
4|from starlette.middleware.cors import CORSMiddleware
5|from motor.motor_asyncio import AsyncIOMotorClient
6|import os
7|import logging
8|from pathlib import Path
9|from pydantic import BaseModel, Field, ConfigDict
10|from typing import Optional, List
11|import uuid
12|from datetime import datetime, timezone
13|import bcrypt
14|import secrets
15|from openpyxl import load_workbook
16|import io
17|
18|ROOT_DIR = Path(__file__).parent
19|load_dotenv(ROOT_DIR / '.env')
20|
21|# MongoDB connection
22|mongo_url = os.environ['MONGO_URL']
23|client = AsyncIOMotorClient(mongo_url)
24|db = client[os.environ['DB_NAME']]
25|
26|# Create the main app without a prefix
27|app = FastAPI()
28|
29|# Create a router with the /api prefix
30|api_router = APIRouter(prefix="/api")
31|
32|# In-memory session store (for production, use Redis)
33|sessions = {}
34|
35|# Models
36|class LoginRequest(BaseModel):
37|    enrollment_number: str
38|    password: str
39|
40|class LoginResponse(BaseModel):
41|    success: bool
42|    message: str
43|    user: Optional[dict] = None
44|    session_token: Optional[str] = None
45|
46|class StudentInfo(BaseModel):
47|    model_config = ConfigDict(extra="ignore")
48|    enrollment_number: str
49|    name: str
50|    branch: str
51|    role: str = "student"
52|
53|class ExamDetails(BaseModel):
54|    model_config = ConfigDict(extra="ignore")
55|    enrollment_number: str
56|    exam_name: str
57|    room_number: str
58|    bench_number: str
59|    block: str
60|    exam_date: str
61|
62|class DashboardResponse(BaseModel):
63|    student: StudentInfo
64|    exams: List[ExamDetails]
65|
66|class AdminUploadResponse(BaseModel):
67|    success: bool
68|    message: str
69|    students_added: int
70|    exams_added: int
71|
72|# Helper functions
73|def hash_password(password: str) -> str:
74|    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
75|
76|def verify_password(password: str, hashed: str) -> bool:
77|    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
78|
79|def generate_session_token() -> str:
80|    return secrets.token_urlsafe(32)
81|
82|async def get_current_user(request: Request):
83|    session_token = request.cookies.get('session_token')
84|    if not session_token or session_token not in sessions:
85|        raise HTTPException(status_code=401, detail="Not authenticated")
86|    return sessions[session_token]
87|
88|# Auth Routes
89|@api_router.post("/auth/login", response_model=LoginResponse)
90|async def login(login_data: LoginRequest, response: Response):
91|    # Find user in database
92|    user = await db.students.find_one(
93|        {"enrollment_number": login_data.enrollment_number},
94|        {"_id": 0}
95|    )
96|    
97|    if not user:
98|        return LoginResponse(success=False, message="Invalid enrollment number or password")
99|    
100|    # Verify password
101|    if not verify_password(login_data.password, user['password_hash']):
102|        return LoginResponse(success=False, message="Invalid enrollment number or password")
103|    
104|    # Create session
105|    session_token = generate_session_token()
106|    sessions[session_token] = {
107|        "enrollment_number": user['enrollment_number'],
108|        "name": user['name'],
109|        "branch": user['branch'],
110|        "role": user['role']
111|    }
112|    
113|    # Set cookie
114|    response.set_cookie(
115|        key="session_token",
116|        value=session_token,
117|        httponly=True,
118|        max_age=86400,  # 24 hours
119|        samesite="lax"
120|    )
121|    
122|    user_data = {
123|        "enrollment_number": user['enrollment_number'],
124|        "name": user['name'],
125|        "branch": user['branch'],
126|        "role": user['role']
127|    }
128|    
129|    return LoginResponse(success=True, message="Login successful", user=user_data, session_token=session_token)
130|
131|@api_router.post("/auth/logout")
132|async def logout(request: Request, response: Response):
133|    session_token = request.cookies.get('session_token')
134|    if session_token and session_token in sessions:
135|        del sessions[session_token]
136|    
137|    response.delete_cookie("session_token")
138|    return {"success": True, "message": "Logged out successfully"}
139|
140|@api_router.get("/auth/me")
141|async def get_me(request: Request):
142|    user = await get_current_user(request)
143|    return {"success": True, "user": user}
144|
145|# Student Routes
146|@api_router.get("/student/dashboard", response_model=DashboardResponse)
147|async def get_student_dashboard(request: Request):
148|    user = await get_current_user(request)
149|    
150|    # Get student info
151|    student = await db.students.find_one(
152|        {"enrollment_number": user['enrollment_number']},
153|        {"_id": 0, "password_hash": 0}
154|    )
155|    
156|    if not student:
157|        raise HTTPException(status_code=404, detail="Student not found")
158|    
159|    # Get exam details
160|    exams = await db.exams.find(
161|        {"enrollment_number": user['enrollment_number']},
162|        {"_id": 0}
163|    ).to_list(100)
164|    
165|    return DashboardResponse(
166|        student=StudentInfo(**student),
167|        exams=[ExamDetails(**exam) for exam in exams]
168|    )
169|
170|# Admin Routes
171|@api_router.post("/admin/upload-excel", response_model=AdminUploadResponse)
172|async def upload_excel(request: Request, file: UploadFile = File(...)):
173|    user = await get_current_user(request)
174|    
175|    # Check if user is admin
176|    if user['role'] != 'admin':
177|        raise HTTPException(status_code=403, detail="Admin access required")
178|    
179|    # Validate file type
180|    if not file.filename.endswith(('.xlsx', '.xls')):
181|        raise HTTPException(status_code=400, detail="Only Excel files are allowed")
182|    
183|    try:
184|        # Read Excel file
185|        contents = await file.read()
186|        workbook = load_workbook(io.BytesIO(contents))
187|        sheet = workbook.active
188|        
189|        students_added = 0
190|        exams_added = 0
191|        
192|        # Skip header row
193|        for row in sheet.iter_rows(min_row=2, values_only=True):
194|            if not row[0]:  # Skip empty rows
195|                continue
196|            
197|            enrollment_number = str(row[0])
198|            name = str(row[1])
199|            branch = str(row[2])
200|            password = str(row[3])
201|            exam_name = str(row[4])
202|            room_number = str(row[5])
203|            bench_number = str(row[6])
204|            block = str(row[7])
205|            exam_date = str(row[8])
206|            
207|            # Check if student exists
208|            existing_student = await db.students.find_one({"enrollment_number": enrollment_number})
209|            
210|            if not existing_student:
211|                # Add new student
212|                student_doc = {
213|                    "enrollment_number": enrollment_number,
214|                    "name": name,
215|                    "branch": branch,
216|                    "password_hash": hash_password(password),
217|                    "role": "student"
218|                }
219|                await db.students.insert_one(student_doc)
220|                students_added += 1
221|            
222|            # Add exam details
223|            exam_doc = {
224|                "enrollment_number": enrollment_number,
225|                "exam_name": exam_name,
226|                "room_number": room_number,
227|                "bench_number": bench_number,
228|                "block": block,
229|                "exam_date": exam_date
230|            }
231|            await db.exams.insert_one(exam_doc)
232|            exams_added += 1
233|        
234|        return AdminUploadResponse(
235|            success=True,
236|            message=f"Successfully uploaded data",
237|            students_added=students_added,
238|            exams_added=exams_added
239|        )
240|    
241|    except Exception as e:
242|        raise HTTPException(status_code=400, detail=f"Error processing Excel file: {str(e)}")
243|
244|@api_router.get("/admin/students")
245|async def get_all_students(request: Request):
246|    user = await get_current_user(request)
247|    
248|    if user['role'] != 'admin':
249|        raise HTTPException(status_code=403, detail="Admin access required")
250|    
251|    students = await db.students.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
252|    return {"success": True, "students": students}
253|
254|@api_router.delete("/admin/students/{enrollment_number}")
255|async def delete_student(enrollment_number: str, request: Request):
256|    user = await get_current_user(request)
257|    
258|    if user['role'] != 'admin':
259|        raise HTTPException(status_code=403, detail="Admin access required")
260|    
261|    # Delete student and their exams
262|    await db.students.delete_one({"enrollment_number": enrollment_number})
263|    await db.exams.delete_many({"enrollment_number": enrollment_number})
264|    
265|    return {"success": True, "message": "Student deleted successfully"}
266|
267|# Include the router in the main app
268|app.include_router(api_router)
269|
270|app.add_middleware(
271|    CORSMiddleware,
272|    allow_credentials=True,
273|    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
274|    allow_methods=["*"],
275|    allow_headers=["*"],
276|)
277|
278|# Configure logging
279|logging.basicConfig(
280|    level=logging.INFO,
281|    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
282|)
283|logger = logging.getLogger(__name__)
284|
285|@app.on_event("shutdown")
286|async def shutdown_db_client():
287|    client.close()
288|
289|@app.on_event("startup")
290|async def seed_database():
291|    """Seed database with sample data if empty"""
292|    # Check if admin exists
293|    admin_exists = await db.students.find_one({"role": "admin"})
294|    
295|    if not admin_exists:
296|        # Create admin user
297|        admin_doc = {
298|            "enrollment_number": "ADMIN001",
299|            "name": "Admin User",
300|            "branch": "Administration",
301|            "password_hash": hash_password("admin123"),
302|            "role": "admin"
303|        }
304|        await db.students.insert_one(admin_doc)
305|        logger.info("Admin user created: ADMIN001 / admin123")
306|    
307|    # Check if students exist
308|    student_count = await db.students.count_documents({"role": "student"})
309|    
310|    if student_count == 0:
311|        # Sample students
312|        sample_students = [
313|            {
314|                "enrollment_number": "CSE2021001",
315|                "name": "Rahul Sharma",
316|                "branch": "Computer Science",
317|                "password_hash": hash_password("pass123"),
318|                "role": "student"
319|            },
320|            {
321|                "enrollment_number": "CSE2021002",
322|                "name": "Priya Patel",
323|                "branch": "Computer Science",
324|                "password_hash": hash_password("pass123"),
325|                "role": "student"
326|            },
327|            {
328|                "enrollment_number": "ECE2021001",
329|                "name": "Amit Kumar",
330|                "branch": "Electronics",
331|                "password_hash": hash_password("pass123"),
332|                "role": "student"
333|            },
334|            {
335|                "enrollment_number": "ME2021001",
336|                "name": "Sneha Gupta",
337|                "branch": "Mechanical",
338|                "password_hash": hash_password("pass123"),
339|                "role": "student"
340|            },
341|            {
342|                "enrollment_number": "EE2021001",
343|                "name": "Vikram Singh",
344|                "branch": "Electrical",
345|                "password_hash": hash_password("pass123"),
346|                "role": "student"
347|            }
348|        ]
349|        
350|        await db.students.insert_many(sample_students)
351|        logger.info(f"Inserted {len(sample_students)} sample students")
352|        
353|        # Sample exam data
354|        sample_exams = [
355|            {
356|                "enrollment_number": "CSE2021001",
357|                "exam_name": "Data Structures Mid-Sem",
358|                "room_number": "301",
359|                "bench_number": "15",
360|                "block": "A Block",
361|                "exam_date": "2026-02-15"
362|            },
363|            {
364|                "enrollment_number": "CSE2021001",
365|                "exam_name": "Database Management Mid-Sem",
366|                "room_number": "305",
367|                "bench_number": "22",
368|                "block": "A Block",
369|                "exam_date": "2026-02-18"
370|            },
371|            {
372|                "enrollment_number": "CSE2021002",
373|                "exam_name": "Data Structures Mid-Sem",
374|                "room_number": "301",
375|                "bench_number": "16",
376|                "block": "A Block",
377|                "exam_date": "2026-02-15"
378|            },
379|            {
380|                "enrollment_number": "ECE2021001",
381|                "exam_name": "Signal Processing Mid-Sem",
382|                "room_number": "202",
383|                "bench_number": "08",
384|                "block": "B Block",
385|                "exam_date": "2026-02-16"
386|            },
387|            {
388|                "enrollment_number": "ME2021001",
389|                "exam_name": "Thermodynamics Mid-Sem",
390|                "room_number": "401",
391|                "bench_number": "12",
392|                "block": "C Block",
393|                "exam_date": "2026-02-17"
394|            },
395|            {
396|                "enrollment_number": "EE2021001",
397|                "exam_name": "Power Systems Mid-Sem",
398|                "room_number": "203",
399|                "bench_number": "19",
400|                "block": "B Block",
401|                "exam_date": "2026-02-19"
402|            }
403|        ]
404|        
405|        await db.exams.insert_many(sample_exams)
406|        logger.info(f"Inserted {len(sample_exams)} sample exam records")
407|
[End of file]