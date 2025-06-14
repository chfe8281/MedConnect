from flask import Flask, render_template, request, redirect, url_for, flash, session
import requests
import os
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import cloudinary.api
from cloudinary.utils import cloudinary_url
import traceback


# Load .env file contents into environment variables
load_dotenv()

from __init__ import app
from __init__ import db

cloudinary.config( 
    cloud_name = os.getenv("CLOUD_NAME"), 
    api_key = os.getenv("CLOUD_API_KEY"), 
    api_secret = os.getenv("API_SECRET"),
    secure=True
)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

from models import User, Profile

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    try:
        db.session.execute(text("SELECT 1"))
        print("✅ Connected to database.")
    except Exception as e:
        print("❌ Failed to connect:", e)

@app.route('/', methods=['GET', 'POST'])
def splash():
    return render_template('splash.html')
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    invalid = False
    message = ""
    if request.method == 'POST':
        username = request.form['username']
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            invalid = True
            message = "Email already registered"
            print("email already registered")
            return render_template('register.html', invalid = invalid, flag = message)

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Create new user
        new_user = User(username = username, name=name, email=email, password=hashed_password, avatar_url = 'img/default_avatar.png')

        # Add and commit to the database
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    invalid = False
    message = ""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        users = User.query.filter_by(email=email).first()
        if users and check_password_hash(users.password, password):
            print(users.email, users.name)
            login_user(users)
            print("success")
            if users.first_login == False:
                users.first_login = True;
                db.session.commit()
                return redirect(url_for('createProfile'))
            return redirect(url_for('dash'))  # Or wherever you want to redirect
        else:
            invalid = True
            message = 'Invalid email or password.'
            print("failed login")

    return render_template('login.html', invalid = invalid, flag = message)

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dash():
    return render_template('dashboard.html', user = current_user.name, avatar_url = current_user.avatar_url)



ALLOWED_EXTENSIONS = ['png', 'jpeg', 'jpg']



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_avatar_to_cloudinary(_file, user_id):
    if _file and allowed_file(_file.filename):
        filename = secure_filename(_file.filename)
        
        # Upload directly to Cloudinary
        try:
            upload_result = cloudinary.uploader.upload(
                _file,
                folder="avatars",  # optional folder
                public_id=f"user_{user_id}_{filename.rsplit('.', 1)[0]}",
                overwrite=True,
                resource_type="image"
            )
            print("Upload success:", upload_result['secure_url'])
            return upload_result['secure_url']
        except Exception as e:
            print("Cloudinary upload error:", e)
            return None
        
@app.route('/createProfile', methods=['GET', 'POST'])
@login_required
def createProfile():
    
    existing_profile = Profile.query.filter_by(user_id=current_user.user_id).first()
    existing_avatar_url = existing_profile.avatar_url if existing_profile else None
    
    if request.method == 'POST':
        bio = request.form['bio']
        location = request.form['location']
        status = request.form['user_type']
        interests = request.form.getlist('interests[]')
        conditions = request.form.getlist('conditions[]')
        file = request.files['avatar_file']
        url = upload_avatar_to_cloudinary(file, current_user.user_id)
        print(url)
        if existing_profile:
            existing_profile.bio = bio
            existing_profile.location = location
            existing_profile.status = status
            existing_profile.interests = interests
            existing_profile.conditions = conditions
            if file and file.filename != '':
                existing_profile.avatar_url = url
                current_user.avatar_url = url
            else:
                existing_profile.avatar_url= existing_avatar_url
                current_user.avatar_url = existing_avatar_url
            
        else: 
            new_profile = Profile(
                user_id = current_user.user_id, 
                bio = bio, status = status, 
                location = location, 
                interests = interests, 
                conditions = conditions, 
                avatar_url = url)
            db.session.add(new_profile)
            current_user.avatar_url = url
        db.session.commit()
        
        print("Profile Created!")
        return redirect(url_for('showProfile'))
    
    elif request.method == "GET":
        if existing_profile:
            return render_template('createProfile.html', name = current_user.name, bio = existing_profile.bio, status = existing_profile.status, location = existing_profile.location, interests = existing_profile.interests, conditions = existing_profile.conditions, avatar_url = current_user.avatar_url)
        else:
            return render_template('createProfile.html')  
            
    return render_template('createProfile.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def showProfile():
    if request.method == "GET":
        profile = Profile.query.filter_by(user_id=current_user.user_id).first()
        if not profile:
            return redirect(url_for('createProfile'))
        
        print(profile.avatar_url)

        
        return render_template('showProfile.html', name = current_user.name, bio = profile.bio, status = profile.status, location = profile.location, interests = ", ".join(profile.interests), conditions = ", ".join(profile.conditions), avatar_url = current_user.avatar_url)
    return render_template('showProfile.html')
    

API_KEY = os.getenv('API_KEY')
AUTH_ENDPOINT = "https://utslogin.nlm.nih.gov/cas/v1/api-key"
SEARCH_ENDPOINT = "https://uts-ws.nlm.nih.gov/rest/search/current"
DEFINITIONS_ENDPOINT = "https://uts-ws.nlm.nih.gov/rest/content/current/CUI"
def get_tgt(api_key):
    params = {'apikey': api_key}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(AUTH_ENDPOINT, data=params, headers=headers)
    if response.status_code == 201:
        tgt_url = response.headers['location']
        return tgt_url
    return None

def get_service_ticket(tgt_url):
    params = {'service': 'http://umlsks.nlm.nih.gov'}
    response = requests.post(tgt_url, data=params)
    print("service ticket", response.text)
    return response.text if response.status_code == 200 else None

def get_definitions(cui, st, language= "ENG"):
    rootsource_map = {
        "ENG": ["MSH", "HPO", "NCI"] # Common English sources
    }
    url = f"https://uts-ws.nlm.nih.gov/rest/content/2023AA/CUI/{cui}/definitions"
    params = {"ticket": st}
    response = requests.get(url, params)
    print("Reponse text", response.text)
    print("Response url", response.url)
    if response.status_code == 200:
        defs = response.json()['result']
        allowed_sources = rootsource_map.get(language.upper(), [])
        filtered_defs = [d.get("value") for d in defs if d.get("rootSource") in allowed_sources and d.get("value")]
        print("Filtered defs")
        return filtered_defs or ["No definitions available in this version."]
    print("not 200")
    return ["Definition lookup failed."]

@app.route('/search', methods=['GET', 'POST'])
@login_required
def index():
    search_results = []
    error = None
    if request.method == 'POST':
        query = request.form['query']
        tgt = get_tgt(API_KEY)
        if tgt:
            st = get_service_ticket(tgt)
            if st:
                params = {
                    'string': query,
                    'ticket': st
                }
                response = requests.get(SEARCH_ENDPOINT, params=params)
                if response.status_code == 200:
                    search_items = response.json()['result']['results']
                    for item in search_items[:5]:  # limit to top 5 for speed
                        cui = item.get('ui')
                        name = item.get('name')
                        print("CUI", cui)
                        if cui and cui != 'NONE':
                            tgt = get_tgt(API_KEY)
                            st = get_service_ticket(tgt)
                            definitions = get_definitions(cui, st)
                            search_results.append({
                                'name': name,
                                'cui': cui,
                                'definitions': definitions
                            })
                else:
                    error = "Failed to fetch search results."
            else:
                error = "Failed to get service ticket."
        else:
            error = "Failed to get authentication ticket."

    return render_template('index.html', results=search_results, error=error)

@app.route('/logout', methods = ['GET', 'POST'])
@login_required
def logout():
    logout_user()
    flash("You have been logged out")
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)