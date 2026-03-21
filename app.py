from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import fitz
import os
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
import tempfile
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
app.config['SECRET_KEY'] = 'your-secret-key-change-this-123'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to use the app.'

# Initialize Groq
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
# ─── Database Models ───────────────────────────────────────────

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    reports_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports = db.relationship('Report', backref='user', lazy=True)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    english_explanation = db.Column(db.Text, nullable=False)
    gujarati_explanation = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── Helper Functions ──────────────────────────────────────────

def extract_text_from_pdf(filepath):
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text.strip()

def get_ai_explanation(text):
    prompt = f"""You are a helpful assistant that explains complex documents to ordinary people.

A user has uploaded a document. Here is the extracted text:

---
{text[:3000]}
---

Please provide:

1. SIMPLE ENGLISH EXPLANATION:
Write a clear, simple explanation of this document in easy English.
- Use short sentences
- Avoid technical jargon
- Explain what it means for the person
- Use bullet points where helpful
- Maximum 200 words

2. GUJARATI EXPLANATION (ગુજરાતી સમજૂતી):
Write the same explanation in simple, everyday Gujarati language.
- Use simple Gujarati words that common people understand
- Same bullet point structure
- Maximum 200 words

Format your response exactly like this:

ENGLISH_EXPLANATION:
[your English explanation here]

GUJARATI_EXPLANATION:
[your Gujarati explanation here]"""

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        max_tokens=1500,
    )

    response_text = chat_completion.choices[0].message.content
    english = ""
    gujarati = ""

    if "ENGLISH_EXPLANATION:" in response_text and "GUJARATI_EXPLANATION:" in response_text:
        parts = response_text.split("GUJARATI_EXPLANATION:")
        english = parts[0].replace("ENGLISH_EXPLANATION:", "").strip()
        gujarati = parts[1].strip()
    else:
        english = response_text
        gujarati = "સમજૂતી મેળવવામાં સમસ્યા આવી. કૃપા કરી ફરીથી પ્રયાસ કરો."

    return english, gujarati

# ─── Routes ────────────────────────────────────────────────────

FREE_REPORT_LIMIT = 2

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    reports_left = FREE_REPORT_LIMIT - current_user.reports_used

    if request.method == 'POST':

        # Check free limit
        if current_user.reports_used >= FREE_REPORT_LIMIT:
            return render_template('index.html',
                error="You have used your 2 free reports. Upgrade to continue.",
                reports_left=0)

        if 'pdf_file' not in request.files:
            return render_template('index.html', error="Please select a PDF file.", reports_left=reports_left)

        file = request.files['pdf_file']

        if file.filename == '':
            return render_template('index.html', error="No file selected.", reports_left=reports_left)

        if not file.filename.endswith('.pdf'):
            return render_template('index.html', error="Only PDF files are allowed.", reports_left=reports_left)

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        extracted_text = extract_text_from_pdf(filepath)

        if not extracted_text:
            return render_template('index.html',
                error="Could not extract text. PDF may be image-based.",
                reports_left=reports_left)

        try:
            english_explanation, gujarati_explanation = get_ai_explanation(extracted_text)
        except Exception as e:
            return render_template('index.html', error=f"AI error: {str(e)}", reports_left=reports_left)

        # Save to database
        report = Report(
            filename=file.filename,
            english_explanation=english_explanation,
            gujarati_explanation=gujarati_explanation,
            user_id=current_user.id
        )
        db.session.add(report)

        # Update usage count
        current_user.reports_used += 1
        db.session.commit()

        return render_template('result.html',
            english=english_explanation,
            gujarati=gujarati_explanation,
            filename=file.filename)

    return render_template('index.html', reports_left=reports_left)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name').strip()
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')

        if not name or not email or not password:
            return render_template('signup.html', error="All fields are required.")

        if len(password) < 6:
            return render_template('signup.html', error="Password must be at least 6 characters.")

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return render_template('signup.html', error="Email already registered. Please log in.")

        hashed_password = generate_password_hash(password)
        new_user = User(name=name, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for('index'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            return render_template('login.html', error="Invalid email or password.")

        login_user(user)
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/history')
@login_required
def history():
    reports = Report.query.filter_by(user_id=current_user.id)\
        .order_by(Report.created_at.desc()).all()
    return render_template('history.html', reports=reports)


@app.route('/history/<int:report_id>')
@login_required
def view_report(report_id):
    report = Report.query.get_or_404(report_id)
    if report.user_id != current_user.id:
        return redirect(url_for('history'))
    return render_template('result.html',
        english=report.english_explanation,
        gujarati=report.gujarati_explanation,
        filename=report.filename)


# ─── Init DB & Run ─────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
