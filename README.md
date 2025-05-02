# Flask Authentication App

A simple Flask application with user authentication functionality.

## Features

- User registration with username and email validation
- Secure password hashing
- User login with remember me option
- Protected routes that require authentication
- User dashboard with account information
- Logout functionality

## Prerequisites

- Python 3.7 or higher
- pip (Python package installer)

## Installation

1. Clone this repository or download the source code.

2. Create a virtual environment (recommended):
   ```
   python -m venv venv
   ```

3. Activate the virtual environment:
   - On Windows:
     ```
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```
     source venv/bin/activate
     ```

4. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Running the Application

1. Make sure your virtual environment is activated.

2. Run the Flask application:
   ```
   python app.py
   ```

3. Open your web browser and navigate to `http://127.0.0.1:5000/`

## Project Structure

- `app.py`: Main application file with routes and configuration
- `models.py`: Database models for users and other data
- `templates/`: HTML templates for the frontend
- `site.db`: SQLite database file (created when the app runs for the first time)

## Security Features

- Password hashing using Werkzeug's security functions
- Protection against session fixation and CSRF
- Login required decorator for protected routes
- Remember me functionality for persistent sessions 