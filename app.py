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

def detect_document_type(text):
    """Auto-detect what kind of document this is"""
    text_lower = text.lower()
    
    medical_keywords = ['hemoglobin', 'blood', 'glucose', 'mri', 'x-ray', 'diagnosis', 
                        'patient', 'doctor', 'hospital', 'mg/dl', 'wbc', 'rbc', 'platelet',
                        'cholesterol', 'thyroid', 'urine', 'creatinine', 'bilirubin']
    bank_keywords = ['account', 'balance', 'transaction', 'debit', 'credit', 'statement',
                     'bank', 'withdrawal', 'deposit', 'ifsc', 'savings', 'current', 'upi']
    legal_keywords = ['agreement', 'contract', 'clause', 'party', 'hereby', 'whereas',
                      'terms', 'conditions', 'legal', 'court', 'plaintiff', 'defendant']
    academic_keywords = ['grade', 'marks', 'score', 'semester', 'cgpa', 'sgpa', 'result',
                         'university', 'college', 'subject', 'pass', 'fail', 'percentage']
    
    scores = {
        'medical': sum(1 for k in medical_keywords if k in text_lower),
        'bank': sum(1 for k in bank_keywords if k in text_lower),
        'legal': sum(1 for k in legal_keywords if k in text_lower),
        'academic': sum(1 for k in academic_keywords if k in text_lower),
    }
    
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'general'


def get_ai_explanation(text):
    """Advanced AI analysis with structured output"""
    
    doc_type = detect_document_type(text)
    
    type_instructions = {
        'medical': """This is a MEDICAL REPORT. Pay special attention to:
- Lab values and whether they are normal/abnormal/critical
- Any diagnoses or findings mentioned
- Medications prescribed
- Risk factors for the patient's health""",

        'bank': """This is a BANK STATEMENT. Pay special attention to:
- Account balance and trends
- Large or unusual transactions
- Recurring charges or subscriptions
- Overall financial health indicators""",

        'legal': """This is a LEGAL DOCUMENT. Pay special attention to:
- Key obligations and rights of each party
- Important dates and deadlines
- Penalty or consequence clauses
- Any unusual or concerning terms""",

        'academic': """This is an ACADEMIC DOCUMENT. Pay special attention to:
- Overall performance and grades
- Subjects that need improvement
- Achievements and strengths
- Impact on academic standing""",

        'general': """This is a general document. Extract the most important information."""
    }

    prompt = f"""You are an expert AI analyst specializing in document analysis. 
You explain complex documents to ordinary people in simple, clear language.

DOCUMENT TYPE: {doc_type.upper()}
{type_instructions[doc_type]}

DOCUMENT TEXT:
---
{text[:4000]}
---

Provide a comprehensive analysis in the following EXACT format. 
Do not deviate from this format:

DOCUMENT_TYPE: {doc_type}

CONFIDENCE_SCORE: [Give a percentage 0-100 of how confident you are in your analysis]

RISK_LEVEL: [Choose exactly one: NORMAL or ATTENTION or CRITICAL]
RISK_REASON: [One sentence explaining the risk level]

KEY_FINDINGS:
- [Finding 1 - most important]
- [Finding 2]
- [Finding 3]
- [Finding 4 if applicable]
- [Finding 5 if applicable]

SIMPLE_EXPLANATION:
[Write 3-4 sentences explaining the document in very simple English that anyone can understand. No jargon.]

ACTION_ITEMS:
- [Specific action 1 the person should take]
- [Specific action 2]
- [Specific action 3 if applicable]

GUJARATI_EXPLANATION:
[Write the same simple explanation in everyday Gujarati. Use simple words.]

GUJARATI_KEY_FINDINGS:
- [Finding 1 in Gujarati]
- [Finding 2 in Gujarati]
- [Finding 3 in Gujarati]

GUJARATI_ACTION_ITEMS:
- [Action 1 in Gujarati]
- [Action 2 in Gujarati]
- [Action 3 in Gujarati if applicable]"""

    chat_completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        max_tokens=2500,
        temperature=0.3,
    )

    response = chat_completion.choices[0].message.content
    return parse_ai_response(response, doc_type)


def parse_ai_response(response, doc_type):
    """Parse the structured AI response into a clean dictionary"""
    
    result = {
        'doc_type': doc_type,
        'confidence': '85',
        'risk_level': 'NORMAL',
        'risk_reason': 'No significant concerns found.',
        'key_findings': [],
        'simple_explanation': '',
        'action_items': [],
        'gujarati_explanation': '',
        'gujarati_key_findings': [],
        'gujarati_action_items': [],
    }

    def extract_section(text, start_marker, end_markers):
        """Extract content between markers"""
        if start_marker not in text:
            return ''
        start = text.index(start_marker) + len(start_marker)
        end = len(text)
        for marker in end_markers:
            if marker in text[start:]:
                end = start + text[start:].index(marker)
                break
        return text[start:end].strip()

    def extract_bullets(text, marker, end_markers):
        """Extract bullet points from a section"""
        section = extract_section(text, marker, end_markers)
        bullets = []
        for line in section.split('\n'):
            line = line.strip()
            if line.startswith('•') or line.startswith('-') or line.startswith('*'):
                clean = line.lstrip('•-* ').strip()
                if clean:
                    bullets.append(clean)
        return bullets

    # Extract confidence
    if 'CONFIDENCE_SCORE:' in response:
        conf_line = extract_section(response, 'CONFIDENCE_SCORE:', ['RISK_LEVEL:', 'KEY_FINDINGS:'])
        digits = ''.join(filter(str.isdigit, conf_line.split('\n')[0]))
        if digits:
            result['confidence'] = min(int(digits[:3]), 100)

    # Extract risk level
    if 'RISK_LEVEL:' in response:
        risk_line = extract_section(response, 'RISK_LEVEL:', ['RISK_REASON:', 'KEY_FINDINGS:'])
        risk_text = risk_line.split('\n')[0].upper()
        if 'CRITICAL' in risk_text:
            result['risk_level'] = 'CRITICAL'
        elif 'ATTENTION' in risk_text:
            result['risk_level'] = 'ATTENTION'
        else:
            result['risk_level'] = 'NORMAL'

    # Extract risk reason
    if 'RISK_REASON:' in response:
        result['risk_reason'] = extract_section(
            response, 'RISK_REASON:', ['KEY_FINDINGS:', 'SIMPLE_EXPLANATION:']
        ).split('\n')[0].strip()

    # Extract sections
    result['key_findings'] = extract_bullets(
        response, 'KEY_FINDINGS:', ['SIMPLE_EXPLANATION:', 'ACTION_ITEMS:'])
    
    result['simple_explanation'] = extract_section(
        response, 'SIMPLE_EXPLANATION:', ['ACTION_ITEMS:', 'GUJARATI_EXPLANATION:'])
    
    result['action_items'] = extract_bullets(
        response, 'ACTION_ITEMS:', ['GUJARATI_EXPLANATION:', 'GUJARATI_KEY_FINDINGS:'])
    
    result['gujarati_explanation'] = extract_section(
        response, 'GUJARATI_EXPLANATION:', ['GUJARATI_KEY_FINDINGS:', 'GUJARATI_ACTION_ITEMS:'])
    
    result['gujarati_key_findings'] = extract_bullets(
        response, 'GUJARATI_KEY_FINDINGS:', ['GUJARATI_ACTION_ITEMS:', 'END'])
    
    result['gujarati_action_items'] = extract_bullets(
        response, 'GUJARATI_ACTION_ITEMS:', ['END', '---'])

    # Fallback if parsing fails
    if not result['simple_explanation']:
        result['simple_explanation'] = response[:500]
    if not result['gujarati_explanation']:
        result['gujarati_explanation'] = 'સમજૂતી મેળવવામાં સમસ્યા આવી. કૃપા કરી ફરીથી પ્રયાસ કરો.'

    return result

def analyze_symptoms(symptoms_text):
    """Analyze user symptoms and return structured health guidance"""
    
    prompt = f"""You are ArogyaAI, a compassionate AI health assistant for Indian users.
A user has described their symptoms. Provide helpful health guidance in simple language.

IMPORTANT RULES:
- Never diagnose. Always say "possible causes" not "you have"
- Use very simple words that common people understand
- Always recommend seeing a doctor for serious symptoms
- Be caring and reassuring in tone

USER SYMPTOMS:
{symptoms_text}

Respond in this EXACT format:

CONFIDENCE_SCORE: [0-100 how well you understood the symptoms]

RISK_LEVEL: [Choose exactly one: LOW or MEDIUM or HIGH]
RISK_REASON: [One simple sentence why]

POSSIBLE_CAUSES:
- [Possible cause 1 in simple words]
- [Possible cause 2]
- [Possible cause 3 if applicable]

WHAT_IT_MEANS:
[2-3 sentences explaining what these symptoms might mean in very simple English. Be reassuring but honest.]

ACTION_STEPS:
- [Action 1 - most important thing to do]
- [Action 2]
- [Action 3]

HOME_REMEDIES:
- [Simple safe home remedy 1 if applicable]
- [Simple safe home remedy 2 if applicable]

WHEN_TO_SEE_DOCTOR:
[One clear sentence about when they must see a doctor immediately]

GUJARATI_SUMMARY:
[Write a simple 3-4 sentence summary in everyday Gujarati explaining the symptoms and what to do]

GUJARATI_ACTION_STEPS:
- [Action 1 in Gujarati]
- [Action 2 in Gujarati]
- [Action 3 in Gujarati]

DISCLAIMER: આ તબીબી નિદાન નથી. કૃપા કરી ડૉક્ટરની સલાહ લો. / This is not a medical diagnosis. Please consult a doctor."""

    chat_completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        max_tokens=2000,
        temperature=0.3,
    )
    
    response = chat_completion.choices[0].message.content
    return parse_symptoms_response(response)


def parse_symptoms_response(response):
    """Parse symptom analysis response"""
    
    result = {
        'confidence': 80,
        'risk_level': 'LOW',
        'risk_reason': 'Symptoms appear mild.',
        'possible_causes': [],
        'what_it_means': '',
        'action_steps': [],
        'home_remedies': [],
        'when_to_see_doctor': 'See a doctor if symptoms worsen or persist.',
        'gujarati_summary': '',
        'gujarati_action_steps': [],
    }

    def extract_section(text, start_marker, end_markers):
        if start_marker not in text:
            return ''
        start = text.index(start_marker) + len(start_marker)
        end = len(text)
        for marker in end_markers:
            if marker in text[start:]:
                end = start + text[start:].index(marker)
                break
        return text[start:end].strip()

    def extract_bullets(text, marker, end_markers):
        section = extract_section(text, marker, end_markers)
        bullets = []
        for line in section.split('\n'):
            line = line.strip()
            if line.startswith(('•', '-', '*')):
                clean = line.lstrip('•-* ').strip()
                if clean:
                    bullets.append(clean)
        return bullets

    # Confidence
    if 'CONFIDENCE_SCORE:' in response:
        conf = extract_section(response, 'CONFIDENCE_SCORE:', ['RISK_LEVEL:'])
        digits = ''.join(filter(str.isdigit, conf.split('\n')[0]))
        if digits:
            result['confidence'] = min(int(digits[:3]), 100)

    # Risk level
    if 'RISK_LEVEL:' in response:
        risk = extract_section(response, 'RISK_LEVEL:', ['RISK_REASON:', 'POSSIBLE_CAUSES:']).split('\n')[0].upper()
        if 'HIGH' in risk:
            result['risk_level'] = 'HIGH'
        elif 'MEDIUM' in risk:
            result['risk_level'] = 'MEDIUM'
        else:
            result['risk_level'] = 'LOW'

    # Risk reason
    if 'RISK_REASON:' in response:
        result['risk_reason'] = extract_section(
            response, 'RISK_REASON:', ['POSSIBLE_CAUSES:', 'WHAT_IT_MEANS:']).split('\n')[0].strip()

    result['possible_causes']       = extract_bullets(response, 'POSSIBLE_CAUSES:', ['WHAT_IT_MEANS:', 'ACTION_STEPS:'])
    result['what_it_means']         = extract_section(response, 'WHAT_IT_MEANS:', ['ACTION_STEPS:', 'HOME_REMEDIES:'])
    result['action_steps']          = extract_bullets(response, 'ACTION_STEPS:', ['HOME_REMEDIES:', 'WHEN_TO_SEE_DOCTOR:'])
    result['home_remedies']         = extract_bullets(response, 'HOME_REMEDIES:', ['WHEN_TO_SEE_DOCTOR:', 'GUJARATI_SUMMARY:'])
    result['when_to_see_doctor']    = extract_section(response, 'WHEN_TO_SEE_DOCTOR:', ['GUJARATI_SUMMARY:', 'GUJARATI_ACTION_STEPS:']).split('\n')[0].strip()
    result['gujarati_summary']      = extract_section(response, 'GUJARATI_SUMMARY:', ['GUJARATI_ACTION_STEPS:', 'DISCLAIMER:'])
    result['gujarati_action_steps'] = extract_bullets(response, 'GUJARATI_ACTION_STEPS:', ['DISCLAIMER:', 'END'])

    if not result['what_it_means']:
        result['what_it_means'] = response[:300]

    return result
# ─── Routes ────────────────────────────────────────────────────
APP_NAME = "ArogyaAI"

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
                analysis = get_ai_explanation(extracted_text)
        except Exception as e:
                return render_template('index.html', 
                    error=f"AI error: {str(e)}", 
                    reports_left=reports_left)

        report = Report(
                filename=file.filename,
                english_explanation=analysis['simple_explanation'],
                gujarati_explanation=analysis['gujarati_explanation'],
                user_id=current_user.id
            )
        db.session.add(report)
        current_user.reports_used += 1
        db.session.commit()

        return render_template('result.html',
                analysis=analysis,
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
app.jinja_env.globals.update(enumerate=enumerate)

# Language strings for UI
TRANSLATIONS = {
    'en': {
        'app_name': 'ArogyaAI',
        'tagline': 'Your AI Health Assistant',
        'nav_reports': 'Reports',
        'nav_symptoms': 'Symptoms',
        'nav_history': 'History',
        'upload_title': 'Understand Any Report',
        'upload_sub': 'Upload your medical report, bank statement or any PDF — explained in simple words instantly.',
        'symptom_title': 'Describe Your Symptoms',
        'symptom_sub': 'Type or speak your symptoms. Our AI will analyze and guide you.',
        'disclaimer': 'This is not a medical diagnosis. Always consult a qualified doctor.',
        'free_left': 'free reports remaining',
    },
    'gu': {
        'app_name': 'આરોગ્યAI',
        'tagline': 'તમારો AI સ્વાસ્થ્ય સહાયક',
        'nav_reports': 'રિપોર્ટ',
        'nav_symptoms': 'લક્ષણો',
        'nav_history': 'ઇતિહાસ',
        'upload_title': 'કોઈ પણ રિપોર્ટ સમજો',
        'upload_sub': 'તમારો મેડિકલ રિપોર્ટ અપલોડ કરો — સરળ ભાષામાં તરત સમજૂતી મેળવો.',
        'symptom_title': 'તમારા લક્ષણો જણાવો',
        'symptom_sub': 'ટાઇપ કરો અથવા બોલો. અમારી AI તમને માર્ગદર્શન આપશે.',
        'disclaimer': 'આ તબીબી નિદાન નથી. ડૉક્ટરની સલાહ અવશ્ય લો.',
        'free_left': 'મફત રિપોર્ટ બાકી',
    }
}

@app.context_processor
def inject_globals():
    lang = request.cookies.get('lang', 'en')
    return dict(lang=lang, t=TRANSLATIONS.get(lang, TRANSLATIONS['en']))

@app.route('/analyze-symptoms', methods=['GET', 'POST'])
@login_required
def analyze_symptoms_route():
    if request.method == 'POST':
        symptoms = request.form.get('symptoms', '').strip()
        
        if not symptoms:
            return render_template('symptoms.html', 
                error="Please describe your symptoms.")
        
        if len(symptoms) < 10:
            return render_template('symptoms.html',
                error="Please describe your symptoms in more detail.")

        try:
            analysis = analyze_symptoms(symptoms)
        except Exception as e:
            return render_template('symptoms.html',
                error=f"AI error: {str(e)}")

        return render_template('symptoms_result.html',
            analysis=analysis,
            symptoms=symptoms)

    return render_template('symptoms.html')

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang not in ['en', 'gu']:
        lang = 'en'
    response = redirect(request.referrer or url_for('index'))
    response.set_cookie('lang', lang, max_age=60*60*24*365)
    return response

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
