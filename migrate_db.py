from app import app, db
from models import User, Message, Group, GroupMembership, GroupMessage
import sqlite3

# Script to migrate the database to include the new bio and profile_image columns

def add_columns():
    """Add the bio and profile_image columns to the User table if they don't exist."""
    try:
        # Connect to the database
        conn = sqlite3.connect('instance/site.db')
        c = conn.cursor()
        
        # Check if bio column exists
        c.execute("PRAGMA table_info(user)")
        columns = c.fetchall()
        column_names = [column[1] for column in columns]
        
        # Add bio column if it doesn't exist
        if 'bio' not in column_names:
            print("Adding 'bio' column to User table...")
            c.execute("ALTER TABLE user ADD COLUMN bio TEXT")
        else:
            print("Bio column already exists.")
        
        # Add profile_image column if it doesn't exist
        if 'profile_image' not in column_names:
            print("Adding 'profile_image' column to User table...")
            c.execute("ALTER TABLE user ADD COLUMN profile_image VARCHAR(120) DEFAULT 'default.jpg'")
        else:
            print("Profile image column already exists.")
        
        # Commit the changes
        conn.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        # Close the connection
        conn.close()

if __name__ == "__main__":
    with app.app_context():
        add_columns() 