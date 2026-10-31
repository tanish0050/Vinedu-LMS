# 🎓 Vinedu LMS — Learning Management System

### A Modern, Full-Stack Learning Management Platform

Vinedu LMS is a web-based Learning Management System designed to provide students with a structured learning experience and administrators with tools to manage courses, student accounts, and learning activities.

🔗 **Live Demo:** https://vinedu-lms-1.onrender.com

---

## 🚀 Project Overview

Vinedu LMS brings learning activities and administrative management together in one platform. It features a web interface, user authentication, persistent learning data, and administrative tools to manage courses and students.

The project focuses on usability, secure authentication, responsive access, and organized learning management.

## ✨ Key Features

### 👨‍🎓 Student Features
- User registration and login
- Personalized learning experience
- Course enrollment and progress tracking
- Learning activity and completion tracking
- Bookmarks and study notes
- Assignments and learning planner
- Flashcards and learning settings
- Profile photo management
- Secure session-based authentication
- Password change functionality

### 🛡️ Administrator Features
- Secure administrator login
- Student account management
- Block and unblock student accounts
- Create and manage courses
- Update course information and topics
- Delete courses
- View student enrollment and quiz activity statistics
- Manage learning-related platform data

### 🔐 Security Features
- Password hashing using Python's `hashlib.scrypt`
- HTTP-only session cookies
- Origin validation for protected operations
- Rate limiting for login and sensitive requests
- Protected administrator routes
- Server-side role verification
- Security-related HTTP response headers
- Environment-based configuration for deployment

## 🧰 Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| Flask | Web application and REST API |
| PostgreSQL | Production database |
| SQLite | Local development database |
| HTML5 | Web page structure |
| CSS3 | Styling and responsive interface |
| JavaScript | Frontend interactions |
| Psycopg | PostgreSQL database connectivity |
| python-dotenv | Environment variable management |
| Render | Cloud deployment |
| Git & GitHub | Version control and source code hosting |

## 🏗️ Application Architecture

The application follows a client-server architecture.

1. **Frontend:** Provides the user interface for students and administrators.
2. **Backend:** Flask handles authentication, API requests, permissions, and business logic.
3. **Database:** Stores users, sessions, courses, and learning information.
4. **Authentication:** Verifies credentials and manages authenticated sessions.
5. **Deployment:** Render hosts the deployed application and connects it to the configured production database.

## 📂 Project Structure

```text
Vinedu-LMS/
│
├── app.py                 # Flask backend and API routes
├── public/
│   ├── index.html         # Main frontend page
│   ├── style.css          # Frontend styling, if present
│   ├── script.js          # Frontend JavaScript, if present
│   └── assets/            # Static assets, if present
│
├── requirements.txt       # Python dependencies
├── .env                   # Local environment variables (not committed)
├── .gitignore             # Files excluded from Git
└── README.md              # Project documentation
```

*Note: The structure above is illustrative. Adjust it to match the actual files in your repository.*

## ⚙️ Local Installation

### Prerequisites

Install the following:
- Python 3.10 or a compatible version
- Git
- A code editor such as Visual Studio Code

### Step 1: Clone the Repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd Vinedu-LMS
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with your actual GitHub repository URL.

### Step 2: Create a Virtual Environment

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

Create a `.env` file in the project root.

Example for local development:

```env
APP_ENV=development
ADMIN_EMAIL=your_admin_email@example.com
ADMIN_PASSWORD=your_strong_local_password
```

Use your own credentials. Never commit the `.env` file or publish real passwords.

For production, configure the environment variables through Render's Environment settings and connect the appropriate PostgreSQL database using `DATABASE_URL`.

### Step 5: Run the Application

```bash
python app.py
```

Open the local address shown by your application, typically:

```text
http://127.0.0.1:3000
```

## ☁️ Deployment

Vinedu LMS is deployed using Render.

**Live Application:** https://vinedu-lms-1.onrender.com

General deployment steps:

1. Push the project to GitHub.
2. Create a web service on Render connected to the repository.
3. Configure the Python environment and install dependencies.
4. Set the start command to `python app.py`, if appropriate for your service configuration.
5. Configure the required environment variables.
6. Connect a PostgreSQL database and configure `DATABASE_URL`.
7. Deploy the application and check the service logs.

### Production Environment Variables

Configure these through Render's Environment settings:

| Variable | Description |
|---|---|
| `APP_ENV` | Set to `production` |
| `DATABASE_URL` | PostgreSQL connection string |
| `ADMIN_EMAIL` | Administrator account email |
| `ADMIN_PASSWORD` | Strong administrator password |
| `ADMIN_RESET_TOKEN` | Secret token for the administrator password-reset endpoint |

Keep all production secrets private. Do not hardcode credentials into frontend JavaScript or expose them through public API responses.

## 🔒 Security Considerations

- Use strong, unique administrator credentials.
- Keep environment variables and database credentials private.
- Do not commit `.env`, database files, or secret tokens.
- Use HTTPS for the deployed application.
- Restrict access to production environment settings.
- Review application logs for deployment errors and authentication issues.
- Back up important production data.

## 🎯 Project Objectives

- Build a full-stack learning management application.
- Provide separate student and administrator experiences.
- Implement secure authentication and session management.
- Support course management and student activity tracking.
- Store application data in a database.
- Deploy a working web application to a cloud hosting platform.
- Demonstrate practical backend development and database integration.

## 🔮 Future Enhancements

Potential improvements include:

- Online quizzes with scoring and result analytics
- Course content uploads and downloadable resources
- Email verification and password recovery
- Notifications and assignment deadlines
- Advanced analytics dashboards
- Additional accessibility improvements
- Automated testing and continuous integration

These are potential enhancements and should not be considered implemented unless they are available in the current application.

## 👨‍💻 Author

**Tanish Kumar**

B.Tech — Computer Science and Engineering (AI & ML)

## 📄 License

Choose and add an appropriate open-source license before redistributing the project. Until a license is added, the repository should not be assumed to grant unrestricted reuse.

---

### 🌐 Explore the Live Project

**Vinedu LMS:** https://vinedu-lms-1.onrender.com

*Built to make learning management more organized, accessible, and secure.*
