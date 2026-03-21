"""
ArogyaAI — AI-powered health assistant for Bharat
Production-grade Flask application
"""

import os
import re
import tempfile
import logging
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request,
    redirect, url_for, jsonify, make_response
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF
from groq import Groq
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS   = {'pdf'}
MAX_CONTENT_MB       = 10
FREE_REPORT_LIMIT    = 2
PAID_REPORTS_PACK    = 25
PLAN_PRICE_INR       = 99
MAX_PDF_CHARS        = 4000
MIN_SYMPTOM_LENGTH   = 15
SUPPORTED_LANGUAGES  = ('en', 'gu')

# ─────────────────────────────────────────────
# APP INIT
# ─────────────────────────────────────────────

app = Flask(__name__)
app.config.update(
    SECRET_KEY                  = os.getenv('SECRET_KEY', 'dev-secret-change-in-prod'),
    SQLALCHEMY_DATABASE_URI     = os.getenv('DATABASE_URL', 'sqlite:///arogyaai.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS = False,
    MAX_CONTENT_LENGTH          = MAX_CONTENT_MB * 1024 * 1024,
    UPLOAD_FOLDER               = tempfile.gettempdir(),
)

db           = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view    = 'login'
login_manager.login_message = ''

groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))

# ─────────────────────────────────────────────
# TRANSLATIONS
# ─────────────────────────────────────────────

TRANSLATIONS = {
    'en': {
        'app_name':       'ArogyaAI',
        'tagline':        'Your AI Health Assistant',
        'nav_reports':    'Reports',
        'nav_symptoms':   'Symptoms',
        'nav_history':    'History',
        'upload_title':   'Understand Any Report',
        'upload_sub':     'Upload your medical report, bank statement or any PDF — explained in simple words instantly.',
        'symptom_title':  'Describe Your Symptoms',
        'symptom_sub':    'Type or speak your symptoms in English or Gujarati. Our AI will guide you.',
        'free_left':      'free reports left',
        'logout':         'Log out',
        'disclaimer':     'This is not a medical diagnosis. Always consult a qualified doctor.',
        'no_reports_yet': 'No reports yet',
        'upload_first':   'Upload your first PDF to get started',
    },
    'gu': {
        'app_name':       'આરોગ્યAI',
        'tagline':        'તમારો AI સ્વાસ્થ્ય સહાયક',
        'nav_reports':    'રિપોર્ટ',
        'nav_symptoms':   'લક્ષણો',
        'nav_history':    'ઇતિહાસ',
        'upload_title':   'કોઈ પણ રિપોર્ટ સમજો',
        'upload_sub':     'તમારો મેડિકલ રિપોર્ટ અપલોડ કરો — સરળ ભાષામાં તરત સમજૂતી મેળવો.',
        'symptom_title':  'તમારા લક્ષણો જણાવો',
        'symptom_sub':    'ટાઇપ કરો અથવા બોલો. અમારી AI તમને માર્ગદર્શન આપશે.',
        'free_left':      'મફત રિપોર્ટ બાકી',
        'logout':         'બહાર',
        'disclaimer':     'આ તબીબી નિદાન નથી. ડૉક્ટરની સલાહ અવશ્ય લો.',
        'no_reports_yet': 'હજી કોઈ રિપોર્ટ નથી',
        'upload_first':   'શરૂ કરવા પ્રથમ PDF અપલોડ કરો',
    }
}

# ─────────────────────────────────────────────
# DATABASE MODELS
# ─────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash  = db.Column(db.String(256), nullable=False)
    reports_used   = db.Column(db.Integer, default=0, nullable=False)
    reports_limit  = db.Column(db.Integer, default=FREE_REPORT_LIMIT, nullable=False)
    is_paid        = db.Column(db.Boolean, default=False, nullable=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    reports = db.relationship('Report', backref='user', lazy='dynamic',
                              cascade='all, delete-orphan')

    @property
    def reports_left(self):
        return max(0, self.reports_limit - self.reports_used)

    @property
    def first_name(self):
        return self.name.split()[0]

    @property
    def initials(self):
        parts = self.name.split()
        return (parts[0][0] + (parts[1][0] if len(parts) > 1 else '')).upper()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


class Report(db.Model):
    __tablename__ = 'reports'

    id                   = db.Column(db.Integer, primary_key=True)
    filename             = db.Column(db.String(255), nullable=False)
    doc_type             = db.Column(db.String(20), default='general')
    risk_level           = db.Column(db.String(10), default='NORMAL')
    english_explanation  = db.Column(db.Text, nullable=False)
    gujarati_explanation = db.Column(db.Text, nullable=False)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id              = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def __repr__(self):
        return f'<Report {self.filename}>'


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────────
# HELPERS — FILE
# ─────────────────────────────────────────────

def allowed_file(filename):
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def extract_text_from_pdf(filepath):
    """Extract plain text from a PDF file. Returns empty string on failure."""
    try:
        doc  = fitz.open(filepath)
        text = '\n'.join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except Exception as e:
        log.error(f'PDF extraction failed: {e}')
        return ''


# ─────────────────────────────────────────────
# HELPERS — AI
# ─────────────────────────────────────────────

_MEDICAL_KW  = {'hemoglobin','blood','glucose','mri','x-ray','diagnosis','patient',
                'doctor','hospital','mg/dl','wbc','rbc','platelet','cholesterol',
                'thyroid','urine','creatinine','bilirubin','prescription','ecg'}
_BANK_KW     = {'account','balance','transaction','debit','credit','statement',
                'bank','withdrawal','deposit','ifsc','savings','upi','neft','rtgs'}
_LEGAL_KW    = {'agreement','contract','clause','party','hereby','whereas','terms',
                'conditions','legal','court','plaintiff','defendant','notary','deed'}
_ACADEMIC_KW = {'grade','marks','score','semester','cgpa','sgpa','result','university',
                'college','subject','pass','fail','percentage','gpa','transcript'}


def detect_document_type(text):
    words = set(re.findall(r'\b\w+\b', text.lower()))
    scores = {
        'medical':  len(words & _MEDICAL_KW),
        'bank':     len(words & _BANK_KW),
        'legal':    len(words & _LEGAL_KW),
        'academic': len(words & _ACADEMIC_KW),
    }
    best  = max(scores, key=scores.get)
    return best if scores[best] >= 2 else 'general'


def _call_groq(prompt, max_tokens=2500):
    """Single place to call Groq API."""
    response = groq_client.chat.completions.create(
        messages=[{'role': 'user', 'content': prompt}],
        model='llama-3.3-70b-versatile',
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return response.choices[0].message.content


def _extract_section(text, start, ends):
    if start not in text:
        return ''
    idx   = text.index(start) + len(start)
    limit = len(text)
    for end in ends:
        pos = text.find(end, idx)
        if pos != -1:
            limit = min(limit, pos)
    return text[idx:limit].strip()


def _extract_bullets(text, start, ends):
    section = _extract_section(text, start, ends)
    results = []
    for line in section.splitlines():
        line = line.strip().lstrip('•–-* ').strip()
        if line and len(line) > 3:
            results.append(line)
    return results


def _parse_confidence(text):
    raw = _extract_section(text, 'CONFIDENCE_SCORE:', ['RISK_LEVEL:', 'KEY_FINDINGS:',
                                                        'POSSIBLE_CAUSES:'])
    digits = ''.join(filter(str.isdigit, raw.split('\n')[0]))
    return min(int(digits[:3]), 100) if digits else 82


def _parse_risk(text):
    raw = _extract_section(text, 'RISK_LEVEL:',
                            ['RISK_REASON:', 'KEY_FINDINGS:', 'POSSIBLE_CAUSES:']).upper()
    if 'CRITICAL' in raw or 'HIGH' in raw:
        return 'HIGH'
    if 'ATTENTION' in raw or 'MEDIUM' in raw:
        return 'MEDIUM'
    return 'LOW'


# ── Report Analysis ──────────────────────────

_REPORT_TYPE_HINTS = {
    'medical':  'Focus on lab values (normal/abnormal), diagnoses, medications, health risks.',
    'bank':     'Focus on balance trends, unusual transactions, recurring charges, financial health.',
    'legal':    'Focus on obligations, rights, deadlines, penalties, unusual clauses.',
    'academic': 'Focus on overall performance, weak subjects, achievements, academic standing.',
    'general':  'Extract the most important information for the reader.',
}


def get_report_analysis(text, doc_type):
    prompt = f"""You are an expert document analyst. Explain this {doc_type} document
to an ordinary person in simple, jargon-free language.

FOCUS: {_REPORT_TYPE_HINTS[doc_type]}

DOCUMENT (first {MAX_PDF_CHARS} chars):
---
{text[:MAX_PDF_CHARS]}
---

Reply in this EXACT format (no extra text before or after):

CONFIDENCE_SCORE: [0-100]

RISK_LEVEL: [LOW or MEDIUM or HIGH]
RISK_REASON: [one plain sentence]

KEY_FINDINGS:
• [finding 1]
• [finding 2]
• [finding 3]
• [finding 4 if relevant]
• [finding 5 if relevant]

SIMPLE_EXPLANATION:
[3-4 plain sentences — what does this document mean for this person?]

ACTION_ITEMS:
• [action 1]
• [action 2]
• [action 3 if needed]

GUJARATI_EXPLANATION:
[Same explanation in simple everyday Gujarati]

GUJARATI_KEY_FINDINGS:
• [finding 1 in Gujarati]
• [finding 2 in Gujarati]
• [finding 3 in Gujarati]

GUJARATI_ACTION_ITEMS:
• [action 1 in Gujarati]
• [action 2 in Gujarati]"""

    raw = _call_groq(prompt)

    _ENDS_AFTER_CONF  = ['RISK_LEVEL:']
    _ENDS_AFTER_RISK  = ['RISK_REASON:', 'KEY_FINDINGS:']
    _ENDS_AFTER_RRSON = ['KEY_FINDINGS:', 'SIMPLE_EXPLANATION:']
    _ENDS_AFTER_KF    = ['SIMPLE_EXPLANATION:', 'ACTION_ITEMS:']
    _ENDS_AFTER_SE    = ['ACTION_ITEMS:', 'GUJARATI_EXPLANATION:']
    _ENDS_AFTER_AI    = ['GUJARATI_EXPLANATION:', 'GUJARATI_KEY_FINDINGS:']
    _ENDS_AFTER_GE    = ['GUJARATI_KEY_FINDINGS:', 'GUJARATI_ACTION_ITEMS:']
    _ENDS_AFTER_GKF   = ['GUJARATI_ACTION_ITEMS:']
    _ENDS_END         = ['---', 'END']

    simple_exp = _extract_section(raw, 'SIMPLE_EXPLANATION:', _ENDS_AFTER_SE)

    return {
        'doc_type':             doc_type,
        'confidence':           _parse_confidence(raw),
        'risk_level':           _parse_risk(raw),
        'risk_reason':          _extract_section(raw, 'RISK_REASON:', _ENDS_AFTER_RRSON).split('\n')[0].strip(),
        'key_findings':         _extract_bullets(raw, 'KEY_FINDINGS:', _ENDS_AFTER_KF),
        'simple_explanation':   simple_exp or raw[:400],
        'action_items':         _extract_bullets(raw, 'ACTION_ITEMS:', _ENDS_AFTER_AI),
        'gujarati_explanation': _extract_section(raw, 'GUJARATI_EXPLANATION:', _ENDS_AFTER_GE)
                                or 'સમજૂતી મેળવવામાં ભૂલ. ફરી પ્રયાસ કરો.',
        'gujarati_key_findings':  _extract_bullets(raw, 'GUJARATI_KEY_FINDINGS:', _ENDS_AFTER_GKF),
        'gujarati_action_items':  _extract_bullets(raw, 'GUJARATI_ACTION_ITEMS:', _ENDS_END),
    }


# ── Symptom Analysis ─────────────────────────

def analyze_symptoms(symptoms_text):
    prompt = f"""You are ArogyaAI, a caring AI health assistant for Indian users.
Analyze these symptoms and give clear, helpful guidance in plain language.

RULES:
- Never diagnose. Say "possible causes" not "you have".
- Use simple words. Avoid medical jargon.
- Be caring but honest.
- Always recommend seeing a doctor for anything serious.

SYMPTOMS: {symptoms_text}

Reply in this EXACT format:

CONFIDENCE_SCORE: [0-100]

RISK_LEVEL: [LOW or MEDIUM or HIGH]
RISK_REASON: [one plain sentence]

POSSIBLE_CAUSES:
• [cause 1]
• [cause 2]
• [cause 3 if relevant]

WHAT_IT_MEANS:
[2-3 plain sentences — what could these symptoms mean?]

ACTION_STEPS:
• [step 1 — most important]
• [step 2]
• [step 3]

HOME_REMEDIES:
• [safe remedy 1 if applicable]
• [safe remedy 2 if applicable]

WHEN_TO_SEE_DOCTOR:
[one clear sentence about when to see a doctor immediately]

GUJARATI_SUMMARY:
[3-4 sentences in simple everyday Gujarati]

GUJARATI_ACTION_STEPS:
• [step 1 in Gujarati]
• [step 2 in Gujarati]
• [step 3 in Gujarati]"""

    raw = _call_groq(prompt, max_tokens=2000)

    what = _extract_section(raw, 'WHAT_IT_MEANS:', ['ACTION_STEPS:', 'HOME_REMEDIES:'])
    gsum = _extract_section(raw, 'GUJARATI_SUMMARY:', ['GUJARATI_ACTION_STEPS:'])
    wtsd = _extract_section(raw, 'WHEN_TO_SEE_DOCTOR:', ['GUJARATI_SUMMARY:']).split('\n')[0].strip()

    return {
        'confidence':           _parse_confidence(raw),
        'risk_level':           _parse_risk(raw),
        'risk_reason':          _extract_section(raw, 'RISK_REASON:', ['POSSIBLE_CAUSES:', 'WHAT_IT_MEANS:']).split('\n')[0].strip(),
        'possible_causes':      _extract_bullets(raw, 'POSSIBLE_CAUSES:', ['WHAT_IT_MEANS:', 'ACTION_STEPS:']),
        'what_it_means':        what or raw[:300],
        'action_steps':         _extract_bullets(raw, 'ACTION_STEPS:', ['HOME_REMEDIES:', 'WHEN_TO_SEE_DOCTOR:']),
        'home_remedies':        _extract_bullets(raw, 'HOME_REMEDIES:', ['WHEN_TO_SEE_DOCTOR:', 'GUJARATI_SUMMARY:']),
        'when_to_see_doctor':   wtsd or 'See a doctor if symptoms worsen or last more than 2-3 days.',
        'gujarati_summary':     gsum or 'સમજૂતી ઉપલબ્ધ નથી.',
        'gujarati_action_steps': _extract_bullets(raw, 'GUJARATI_ACTION_STEPS:', ['---', 'END']),
    }


# ─────────────────────────────────────────────
# CONTEXT PROCESSORS
# ─────────────────────────────────────────────

@app.context_processor
def inject_globals():
    lang = request.cookies.get('lang', 'en')
    if lang not in SUPPORTED_LANGUAGES:
        lang = 'en'
    return dict(
        lang=lang,
        t=TRANSLATIONS[lang],
        app_version='1.0.0',
    )


app.jinja_env.globals.update(enumerate=enumerate)


# ─────────────────────────────────────────────
# ROUTES — AUTH
# ─────────────────────────────────────────────

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not all([name, email, password]):
            error = 'All fields are required.'
        elif len(name) < 2:
            error = 'Name must be at least 2 characters.'
        elif not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            error = 'Please enter a valid email address.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif User.query.filter_by(email=email).first():
            error = 'This email is already registered. Please log in.'
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=True)
            log.info(f'New user registered: {email}')
            return redirect(url_for('index'))

    return render_template('signup.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            error = 'Invalid email or password.'
        else:
            login_user(user, remember=True)
            log.info(f'User logged in: {email}')
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('index'))

    return render_template('login.html', error=error)


@app.route('/logout')
@login_required
def logout():
    log.info(f'User logged out: {current_user.email}')
    logout_user()
    return redirect(url_for('login'))


# ─────────────────────────────────────────────
# ROUTES — LANGUAGE
# ─────────────────────────────────────────────

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang not in SUPPORTED_LANGUAGES:
        lang = 'en'
    referrer = request.referrer or url_for('index')
    response = make_response(redirect(referrer))
    response.set_cookie('lang', lang, max_age=60 * 60 * 24 * 365, samesite='Lax')
    return response


# ─────────────────────────────────────────────
# ROUTES — REPORT UPLOAD
# ─────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        # Usage limit check
        if current_user.reports_used >= current_user.reports_limit:
            return render_template('index.html',
                error='You have used all your free reports. Please upgrade to continue.',
                show_upgrade=True)

        file = request.files.get('pdf_file')

        # Validation
        if not file or file.filename == '':
            return render_template('index.html', error='Please select a PDF file.')
        if not allowed_file(file.filename):
            return render_template('index.html', error='Only PDF files are supported.')

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        try:
            file.save(filepath)
            text = extract_text_from_pdf(filepath)
        except Exception as e:
            log.error(f'File save/extract error: {e}')
            return render_template('index.html', error='Could not read your file. Please try again.')
        finally:
            # Always clean up temp file
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

        if not text:
            return render_template('index.html',
                error='Could not extract text. Your PDF may be scanned/image-based.')

        if len(text.strip()) < 50:
            return render_template('index.html',
                error='PDF has very little text. Please upload a text-based PDF.')

        try:
            doc_type = detect_document_type(text)
            analysis = get_report_analysis(text, doc_type)
        except Exception as e:
            log.error(f'AI analysis error: {e}')
            return render_template('index.html',
                error='AI analysis failed. Please try again in a moment.')

        # Persist to DB
        report = Report(
            filename             = filename,
            doc_type             = analysis['doc_type'],
            risk_level           = analysis['risk_level'],
            english_explanation  = analysis['simple_explanation'],
            gujarati_explanation = analysis['gujarati_explanation'],
            user_id              = current_user.id,
        )
        db.session.add(report)
        current_user.reports_used += 1
        db.session.commit()
        log.info(f'Report analyzed for user {current_user.email}: {filename}')

        return render_template('result.html',
            analysis=analysis,
            filename=filename,
            report_id=report.id)

    return render_template('index.html')


# ─────────────────────────────────────────────
# ROUTES — SYMPTOM ANALYZER
# ─────────────────────────────────────────────

@app.route('/analyze-symptoms', methods=['GET', 'POST'])
@login_required
def analyze_symptoms_route():
    if request.method == 'POST':
        symptoms = request.form.get('symptoms', '').strip()

        if not symptoms:
            return render_template('symptoms.html',
                error='Please describe your symptoms.')
        if len(symptoms) < MIN_SYMPTOM_LENGTH:
            return render_template('symptoms.html',
                error='Please describe your symptoms in more detail (at least a few words).')
        if len(symptoms) > 2000:
            symptoms = symptoms[:2000]

        try:
            analysis = analyze_symptoms(symptoms)
        except Exception as e:
            log.error(f'Symptom analysis error: {e}')
            return render_template('symptoms.html',
                error='AI analysis failed. Please try again.')

        return render_template('symptoms_result.html',
            analysis=analysis,
            symptoms=symptoms)

    return render_template('symptoms.html')


# ─────────────────────────────────────────────
# ROUTES — HISTORY
# ─────────────────────────────────────────────

@app.route('/history')
@login_required
def history():
    page    = request.args.get('page', 1, type=int)
    reports = (Report.query
               .filter_by(user_id=current_user.id)
               .order_by(Report.created_at.desc())
               .paginate(page=page, per_page=20, error_out=False))
    return render_template('history.html', reports=reports)


@app.route('/history/<int:report_id>')
@login_required
def view_report(report_id):
    report = Report.query.get_or_404(report_id)

    # Security: only owner can view
    if report.user_id != current_user.id:
        log.warning(f'Unauthorized report access: user {current_user.id} → report {report_id}')
        return redirect(url_for('history'))

    # Reconstruct minimal analysis dict for result template
    analysis = {
        'doc_type':              report.doc_type,
        'confidence':            90,
        'risk_level':            report.risk_level,
        'risk_reason':           'Previously analyzed report.',
        'key_findings':          [],
        'simple_explanation':    report.english_explanation,
        'action_items':          [],
        'gujarati_explanation':  report.gujarati_explanation,
        'gujarati_key_findings': [],
        'gujarati_action_items': [],
    }
    return render_template('result.html',
        analysis=analysis,
        filename=report.filename,
        report_id=report.id)


# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404,
        message='Page not found.'), 404


@app.errorhandler(413)
def too_large(e):
    return render_template('index.html',
        error=f'File too large. Maximum size is {MAX_CONTENT_MB}MB.'), 413


@app.errorhandler(500)
def server_error(e):
    log.error(f'500 error: {e}')
    return render_template('error.html', code=500,
        message='Something went wrong. Please try again.'), 500


# ─────────────────────────────────────────────
# HEALTH CHECK (for Render / uptime monitors)
# ─────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify(status='ok', version='1.0.0'), 200


# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────

with app.app_context():
    db.create_all()
    log.info('Database tables verified.')

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')