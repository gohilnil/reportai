"""
ArogyaAI — AI-powered health assistant for Bharat
Production-grade Flask application — v3.0
"""

import os
import re
import tempfile
import logging
import hmac as hmac_module
import hashlib
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
import fitz
from groq import Groq
from dotenv import load_dotenv
import razorpay

from flask_dance.contrib.google import make_google_blueprint
from flask_dance.consumer import oauth_authorized
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger('arogyaai')

ALLOWED_EXTENSIONS       = {'pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
MAX_CONTENT_MB           = 10
FREE_REPORT_LIMIT        = 999   # unlimited during launch
MAX_PDF_CHARS            = 4000
MIN_SYMPTOM_LENGTH       = 10
SUPPORTED_LANGUAGES      = ('en', 'gu')

PLANS = {
    'starter': {'name': 'Starter', 'price': 49,  'reports': 10,  'popular': False},
    'popular': {'name': 'Popular', 'price': 99,  'reports': 25,  'popular': True},
    'pro':     {'name': 'Pro',     'price': 199, 'reports': 60,  'popular': False},
}

# ─────────────────────────────────────────────
# APP INIT
# ─────────────────────────────────────────────

app = Flask(__name__)

database_url = os.getenv('DATABASE_URL', 'sqlite:///arogyaai.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config.update(
    SECRET_KEY                     = os.getenv('SECRET_KEY', 'dev-secret-change-in-prod'),
    SQLALCHEMY_DATABASE_URI        = database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS = False,
    MAX_CONTENT_LENGTH             = MAX_CONTENT_MB * 1024 * 1024,
    UPLOAD_FOLDER                  = tempfile.gettempdir(),
)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE']  = '1'

db            = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view    = 'login'
login_manager.login_message = ''

groq_client     = Groq(api_key=os.getenv('GROQ_API_KEY'))
razorpay_client = razorpay.Client(
    auth=(os.getenv('RAZORPAY_KEY_ID', ''), os.getenv('RAZORPAY_KEY_SECRET', ''))
)

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
        'nav_image':      'Image',
        'upload_title':   'Understand Any Report',
        'upload_sub':     'Upload your medical report, bank statement or any PDF — explained in simple words instantly.',
        'symptom_title':  'Describe Your Symptoms',
        'symptom_sub':    'Type or speak your symptoms. Our AI will guide you.',
        'free_left':      'reports left',
        'logout':         'Log out',
        'disclaimer':     'Not a medical diagnosis. Always consult a qualified doctor.',
        'no_reports_yet': 'No reports yet',
        'upload_first':   'Upload your first PDF to get started',
    },
    'gu': {
        'app_name':       'ArogyaAI',
        'tagline':        'તમારો AI સ્વાસ્થ્ય સહાયક',
        'nav_reports':    'રિપોર્ટ',
        'nav_symptoms':   'લક્ષણો',
        'nav_history':    'ઇતિહાસ',
        'nav_image':      'ઇમેજ',
        'upload_title':   'કોઈ પણ રિપોર્ટ સમજો',
        'upload_sub':     'તમારો મેડિકલ રિપોર્ટ અપલોડ કરો — સરળ ભાષામાં તરત સમજૂતી મેળવો.',
        'symptom_title':  'તમારા લક્ષણો જણાવો',
        'symptom_sub':    'ટાઇપ કરો અથવા બોલો. AI તમને માર્ગદર્શન આપશે.',
        'free_left':      'રિપોર્ટ બાકી',
        'logout':         'બહાર',
        'disclaimer':     'આ તબીબી નિદાન નથી. ડૉક્ટરની સલાહ અવશ્ય લો.',
        'no_reports_yet': 'હજી કોઈ રિપોર્ટ નથી',
        'upload_first':   'શરૂ કરવા પ્રથમ PDF અપલોડ કરો',
    }
}

# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer,    primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    reports_used  = db.Column(db.Integer, default=0,                 nullable=False)
    reports_limit = db.Column(db.Integer, default=FREE_REPORT_LIMIT, nullable=False)
    is_paid       = db.Column(db.Boolean, default=False,             nullable=False)
    is_admin      = db.Column(db.Boolean, default=False,             nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow,  nullable=False)
    reports       = db.relationship('Report',  backref='user', lazy='dynamic', cascade='all, delete-orphan')
    payments      = db.relationship('Payment', backref='user', lazy='dynamic')

    @property
    def reports_left(self):
        return max(0, self.reports_limit - self.reports_used)

    @property
    def first_name(self):
        return self.name.split()[0] if self.name else 'User'

    @property
    def initials(self):
        parts = self.name.strip().split()
        if not parts:
            return 'U'
        return (parts[0][0] + (parts[1][0] if len(parts) > 1 else '')).upper()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


class OAuth(db.Model):
    __tablename__    = 'oauth'
    id               = db.Column(db.Integer,    primary_key=True)
    provider         = db.Column(db.String(50),  nullable=False)
    provider_user_id = db.Column(db.String(256), nullable=False)
    token            = db.Column(db.JSON,         nullable=False)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    user             = db.relationship('User', backref='oauth_tokens')


class Report(db.Model):
    __tablename__        = 'reports'
    id                   = db.Column(db.Integer,     primary_key=True)
    filename             = db.Column(db.String(255), nullable=False)
    doc_type             = db.Column(db.String(20),  default='general')
    risk_level           = db.Column(db.String(10),  default='LOW')
    english_explanation  = db.Column(db.Text,        nullable=False)
    gujarati_explanation = db.Column(db.Text,        nullable=False)
    created_at           = db.Column(db.DateTime,    default=datetime.utcnow, nullable=False)
    user_id              = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class Payment(db.Model):
    __tablename__       = 'payments'
    id                  = db.Column(db.Integer,    primary_key=True)
    razorpay_order_id   = db.Column(db.String(100), nullable=False, unique=True)
    razorpay_payment_id = db.Column(db.String(100), nullable=True)
    plan_id             = db.Column(db.String(20),  nullable=False)
    amount              = db.Column(db.Integer,     nullable=False)
    status              = db.Column(db.String(20),  default='created')
    created_at          = db.Column(db.DateTime,    default=datetime.utcnow)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# ─────────────────────────────────────────────
# GOOGLE OAUTH  ← BUG FIXED: provider field was set to google_user_id
# ─────────────────────────────────────────────

google_bp = make_google_blueprint(
    client_id     = os.getenv('GOOGLE_CLIENT_ID'),
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET'),
    scope         = ['openid', 'email', 'profile'],
    storage       = SQLAlchemyStorage(OAuth, db.session, user=current_user, user_required=False),
)
app.register_blueprint(google_bp, url_prefix='/login')


@app.route('/login/google/start')
def google_login():
    return redirect(url_for('google.login'))


@oauth_authorized.connect_via(google_bp)
def google_logged_in(blueprint, token):
    if not token:
        return False
    resp = blueprint.session.get('/oauth2/v2/userinfo')
    if not resp.ok:
        return False

    info           = resp.json()
    google_user_id = str(info['id'])
    email          = info.get('email', '')
    name           = info.get('name', 'User')

    oauth_record = OAuth.query.filter_by(
        provider='google', provider_user_id=google_user_id).first()

    if oauth_record:
        login_user(oauth_record.user, remember=True)
        return False

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(name=name, email=email)
        user.set_password(os.urandom(24).hex())
        db.session.add(user)
        db.session.flush()

    oauth_record = OAuth(
        provider         = 'google',           # ← FIXED (was google_user_id)
        provider_user_id = google_user_id,
        token            = token,
        user_id          = user.id,
    )
    db.session.add(oauth_record)
    db.session.commit()
    login_user(user, remember=True)
    log.info(f'Google login: {email}')
    return False

# ─────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────
# AI HELPERS
# ─────────────────────────────────────────────

_MEDICAL_KW  = {'hemoglobin','blood','glucose','mri','x-ray','diagnosis','patient',
                'doctor','hospital','mg/dl','wbc','rbc','platelet','cholesterol',
                'thyroid','urine','creatinine','bilirubin','prescription','ecg',
                'bp','pressure','temperature','fever','infection','test','report'}
_BANK_KW     = {'account','balance','transaction','debit','credit','statement',
                'bank','withdrawal','deposit','ifsc','savings','upi','neft','rtgs',
                'cheque','interest','loan','emi','passbook','ledger'}
_LEGAL_KW    = {'agreement','contract','clause','party','hereby','whereas','terms',
                'conditions','legal','court','plaintiff','defendant','notary','deed',
                'affidavit','witness','jurisdiction','warrant','penalty','liable'}
_ACADEMIC_KW = {'grade','marks','score','semester','cgpa','sgpa','result','university',
                'college','subject','pass','fail','percentage','gpa','transcript',
                'attendance','exam','paper','degree','diploma'}


def detect_document_type(text):
    words = set(re.findall(r'\b\w+\b', text.lower()))
    scores = {
        'medical':  len(words & _MEDICAL_KW),
        'bank':     len(words & _BANK_KW),
        'legal':    len(words & _LEGAL_KW),
        'academic': len(words & _ACADEMIC_KW),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else 'general'


def _call_groq(prompt, max_tokens=2500):
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
        if 0 < pos < limit:
            limit = pos
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
    raw    = _extract_section(text, 'CONFIDENCE_SCORE:', ['RISK_LEVEL:', 'KEY_FINDINGS:', 'POSSIBLE_CAUSES:'])
    digits = ''.join(filter(str.isdigit, raw.split('\n')[0]))
    return min(int(digits[:3]), 100) if digits else 82


def _parse_risk(text):
    raw = _extract_section(text, 'RISK_LEVEL:',
                            ['RISK_REASON:', 'KEY_FINDINGS:', 'POSSIBLE_CAUSES:']).upper()
    if 'HIGH' in raw or 'CRITICAL' in raw:
        return 'HIGH'
    if 'MEDIUM' in raw or 'ATTENTION' in raw:
        return 'MEDIUM'
    return 'LOW'


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _safe_remove(filepath):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        log.warning(f'Could not remove temp file {filepath}: {e}')


def extract_text_from_pdf(filepath):
    """Extract text from PDF — tries 3 methods, returns best result."""
    try:
        doc        = fitz.open(filepath)
        pages_text = []
        for page in doc:
            # Method 1: direct
            page_text = page.get_text('text')
            # Method 2: dict blocks
            if len(page_text.strip()) < 20:
                try:
                    blocks = page.get_text('dict')['blocks']
                    spans  = []
                    for block in blocks:
                        if block.get('type') == 0:
                            for line in block.get('lines', []):
                                for span in line.get('spans', []):
                                    spans.append(span.get('text', ''))
                    page_text = ' '.join(spans)
                except Exception:
                    pass
            # Method 3: rawtext
            if len(page_text.strip()) < 20:
                try:
                    page_text = page.get_text('rawtext')
                except Exception:
                    pass
            pages_text.append(page_text)
        doc.close()
        text   = '\n'.join(pages_text)
        lines  = [l.strip() for l in text.splitlines() if l.strip()]
        result = '\n'.join(lines)
        log.info(f'PDF extracted: {len(result)} chars')
        return result
    except Exception as e:
        log.error(f'PDF extraction failed: {e}')
        return ''


_REPORT_HINTS = {
    'medical':  'Focus on lab values (normal/abnormal), diagnoses, medications, health risks.',
    'bank':     'Focus on balance trends, unusual transactions, recurring charges, financial health.',
    'legal':    'Focus on obligations, rights, deadlines, penalties, unusual clauses.',
    'academic': 'Focus on overall performance, weak subjects, achievements, academic standing.',
    'general':  'Extract the most important information for the reader.',
}


def get_report_analysis(text, doc_type):
    prompt = f"""You are an expert document analyst. Explain this {doc_type} document
to an ordinary person in simple, jargon-free language.

FOCUS: {_REPORT_HINTS[doc_type]}

DOCUMENT:
---
{text[:MAX_PDF_CHARS]}
---

Reply in this EXACT format:

CONFIDENCE_SCORE: [0-100]

RISK_LEVEL: [LOW or MEDIUM or HIGH]
RISK_REASON: [one plain sentence]

KEY_FINDINGS:
• [finding 1]
• [finding 2]
• [finding 3]

SIMPLE_EXPLANATION:
[3-4 plain sentences]

ACTION_ITEMS:
• [action 1]
• [action 2]
• [action 3]

GUJARATI_EXPLANATION:
[Same 3-4 sentences in simple Gujarati]

GUJARATI_KEY_FINDINGS:
• [finding 1 in Gujarati]
• [finding 2 in Gujarati]

GUJARATI_ACTION_ITEMS:
• [action 1 in Gujarati]
• [action 2 in Gujarati]"""

    raw        = _call_groq(prompt)
    simple_exp = _extract_section(raw, 'SIMPLE_EXPLANATION:', ['ACTION_ITEMS:', 'GUJARATI_EXPLANATION:'])
    return {
        'doc_type':              doc_type,
        'confidence':            _parse_confidence(raw),
        'risk_level':            _parse_risk(raw),
        'risk_reason':           _extract_section(raw, 'RISK_REASON:', ['KEY_FINDINGS:', 'SIMPLE_EXPLANATION:']).split('\n')[0].strip(),
        'key_findings':          _extract_bullets(raw, 'KEY_FINDINGS:', ['SIMPLE_EXPLANATION:', 'ACTION_ITEMS:']),
        'simple_explanation':    simple_exp or raw[:400],
        'action_items':          _extract_bullets(raw, 'ACTION_ITEMS:', ['GUJARATI_EXPLANATION:', 'GUJARATI_KEY_FINDINGS:']),
        'gujarati_explanation':  _extract_section(raw, 'GUJARATI_EXPLANATION:', ['GUJARATI_KEY_FINDINGS:', 'GUJARATI_ACTION_ITEMS:']) or 'સમજૂતી ઉપલબ્ધ નથી.',
        'gujarati_key_findings': _extract_bullets(raw, 'GUJARATI_KEY_FINDINGS:', ['GUJARATI_ACTION_ITEMS:']),
        'gujarati_action_items': _extract_bullets(raw, 'GUJARATI_ACTION_ITEMS:', ['---', 'END']),
    }


def analyze_symptoms(symptoms_text):
    prompt = f"""You are ArogyaAI, a caring AI health assistant for Indian users.

SYMPTOMS: {symptoms_text}

Reply in EXACT format:

CONFIDENCE_SCORE: [0-100]

RISK_LEVEL: [LOW or MEDIUM or HIGH]
RISK_REASON: [one plain sentence]

POSSIBLE_CAUSES:
• [cause 1]
• [cause 2]
• [cause 3]

WHAT_IT_MEANS:
[2-3 plain sentences]

ACTION_STEPS:
• [step 1]
• [step 2]
• [step 3]

HOME_REMEDIES:
• [remedy 1]
• [remedy 2]

WHEN_TO_SEE_DOCTOR:
[one clear sentence]

GUJARATI_SUMMARY:
[3-4 sentences in simple Gujarati]

GUJARATI_ACTION_STEPS:
• [step 1 in Gujarati]
• [step 2 in Gujarati]"""

    raw  = _call_groq(prompt, max_tokens=2000)
    what = _extract_section(raw, 'WHAT_IT_MEANS:', ['ACTION_STEPS:', 'HOME_REMEDIES:'])
    gsum = _extract_section(raw, 'GUJARATI_SUMMARY:', ['GUJARATI_ACTION_STEPS:'])
    wtsd = _extract_section(raw, 'WHEN_TO_SEE_DOCTOR:', ['GUJARATI_SUMMARY:']).split('\n')[0].strip()
    return {
        'confidence':            _parse_confidence(raw),
        'risk_level':            _parse_risk(raw),
        'risk_reason':           _extract_section(raw, 'RISK_REASON:', ['POSSIBLE_CAUSES:', 'WHAT_IT_MEANS:']).split('\n')[0].strip(),
        'possible_causes':       _extract_bullets(raw, 'POSSIBLE_CAUSES:', ['WHAT_IT_MEANS:', 'ACTION_STEPS:']),
        'what_it_means':         what or raw[:300],
        'action_steps':          _extract_bullets(raw, 'ACTION_STEPS:', ['HOME_REMEDIES:', 'WHEN_TO_SEE_DOCTOR:']),
        'home_remedies':         _extract_bullets(raw, 'HOME_REMEDIES:', ['WHEN_TO_SEE_DOCTOR:', 'GUJARATI_SUMMARY:']),
        'when_to_see_doctor':    wtsd or 'See a doctor if symptoms worsen or last more than 2-3 days.',
        'gujarati_summary':      gsum or 'સมجૂтी ઉплбдь нथी.',
        'gujarati_action_steps': _extract_bullets(raw, 'GUJARATI_ACTION_STEPS:', ['---', 'END']),
    }


def _get_mime(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    return {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
            'png': 'image/png', 'webp': 'image/webp',
            'gif': 'image/gif'}.get(ext, 'image/jpeg')


def analyze_image_with_ai(image_path, filename, category='general', context=''):
    import base64
    with open(image_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    hints = {
        'skin':     'Focus on skin condition, color, texture, any visible rash or abnormality.',
        'food':     'Focus on food items visible, nutritional aspects, hygiene concerns.',
        'medicine': 'Focus on identifying medicine, reading visible text, dosage info.',
        'report':   'Focus on extracting and explaining key medical values and findings.',
        'xray':     'Focus on visible bone structure, any abnormalities.',
        'general':  'Provide a general health-related analysis of what you see.',
    }
    context_line = f'\nUser context: "{context}"' if context else ''
    prompt = f"""You are ArogyaAI analyzing a {category} image.
{hints.get(category, hints['general'])}{context_line}
Never give definitive diagnosis. Use simple language.

Reply in EXACT format:

CONFIDENCE_SCORE: [0-100]
RISK_LEVEL: [LOW or MEDIUM or HIGH]
RISK_REASON: [one plain sentence]
WHAT_I_SEE:
[2-3 sentences]
POSSIBLE_ISSUE:
[2-3 sentences]
ACTION_STEPS:
• [action 1]
• [action 2]
• [action 3]
WHEN_TO_SEE_DOCTOR:
[one sentence]
GUJARATI_SUMMARY:
[3-4 sentences in Gujarati]
GUJARATI_ACTION_STEPS:
• [action 1 in Gujarati]
• [action 2 in Gujarati]"""

    response = groq_client.chat.completions.create(
        model='meta-llama/llama-4-scout-17b-16e-instruct',
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': f'data:{_get_mime(filename)};base64,{image_data}'}},
                {'type': 'text', 'text': prompt}
            ]
        }],
        max_tokens=2000,
        temperature=0.3,
    )
    raw = response.choices[0].message.content
    return {
        'confidence':            _parse_confidence(raw),
        'risk_level':            _parse_risk(raw),
        'risk_reason':           _extract_section(raw, 'RISK_REASON:', ['WHAT_I_SEE:', 'POSSIBLE_ISSUE:']).split('\n')[0].strip(),
        'what_i_see':            _extract_section(raw, 'WHAT_I_SEE:', ['POSSIBLE_ISSUE:', 'ACTION_STEPS:']) or 'Could not process image.',
        'possible_issue':        _extract_section(raw, 'POSSIBLE_ISSUE:', ['ACTION_STEPS:', 'WHEN_TO_SEE_DOCTOR:']) or 'No specific concerns identified.',
        'action_steps':          _extract_bullets(raw, 'ACTION_STEPS:', ['WHEN_TO_SEE_DOCTOR:', 'GUJARATI_SUMMARY:']),
        'when_to_see_doctor':    _extract_section(raw, 'WHEN_TO_SEE_DOCTOR:', ['GUJARATI_SUMMARY:']).split('\n')[0].strip() or 'Consult a doctor if concerned.',
        'gujarati_summary':      _extract_section(raw, 'GUJARATI_SUMMARY:', ['GUJARATI_ACTION_STEPS:']) or 'સमजૂтी ઉплбдь нथी.',
        'gujarati_action_steps': _extract_bullets(raw, 'GUJARATI_ACTION_STEPS:', ['---', 'END']),
    }

# ─────────────────────────────────────────────
# CONTEXT PROCESSOR
# ─────────────────────────────────────────────

@app.context_processor
def inject_globals():
    lang = request.cookies.get('lang', 'en')
    if lang not in SUPPORTED_LANGUAGES:
        lang = 'en'
    return dict(lang=lang, t=TRANSLATIONS[lang], request=request)

app.jinja_env.globals.update(enumerate=enumerate, min=min, max=max)

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
        elif not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            error = 'Please enter a valid email address.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif User.query.filter_by(email=email).first():
            error = 'This email is already registered. Please log in.'
        else:
            try:
                user = User(name=name, email=email)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                login_user(user, remember=True)
                log.info(f'New user: {email}')
                return redirect(url_for('index'))
            except Exception as e:
                db.session.rollback()
                log.error(f'Signup DB error: {e}')
                error = 'Could not create account. Please try again.'
    return render_template('signup.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not email or not password:
            error = 'Please enter your email and password.'
        else:
            user = User.query.filter_by(email=email).first()
            if not user or not user.check_password(password):
                error = 'Invalid email or password.'
            else:
                login_user(user, remember=True)
                log.info(f'Login: {email}')
                next_page = request.args.get('next', '')
                if next_page and next_page.startswith('/') and not next_page.startswith('//'):
                    return redirect(next_page)
                return redirect(url_for('index'))
    return render_template('login.html', error=error)


@app.route('/logout')
@login_required
def logout():
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
    response.set_cookie('lang', lang, max_age=60*60*24*365, samesite='Lax')
    return response

# ─────────────────────────────────────────────
# ROUTES — REPORT UPLOAD  ← FULLY FIXED
# ─────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method != 'POST':
        return render_template('index.html')

    file = request.files.get('pdf_file')
    if not file or not file.filename:
        return render_template('index.html', error='Please select a PDF file.')
    if not allowed_file(file.filename):
        return render_template('index.html', error='Only PDF files are supported.')

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f'aai_{filename}')

    # Save
    try:
        file.save(filepath)
    except Exception as e:
        log.error(f'File save error: {e}')
        return render_template('index.html', error='Could not save file. Please try again.')

    # Extract text — cleanup in finally so file is always removed
    text = ''
    try:
        text = extract_text_from_pdf(filepath)
        log.info(f'Extracted {len(text)} chars from {filename}')
    except Exception as e:
        log.error(f'Extraction error: {e}')
    finally:
        _safe_remove(filepath)

    if not text or len(text.strip()) < 10:
        return render_template('index.html',
            error='Could not read this PDF. It may be a scanned or image-only PDF. Try the Image Analyzer instead.',
            show_symptom_link=True)

    # AI Analysis
    try:
        doc_type = detect_document_type(text)
        analysis = get_report_analysis(text, doc_type)
    except Exception as e:
        log.error(f'AI error: {e}')
        return render_template('index.html', error='AI analysis failed. Please try again in a moment.')

    # Save to DB
    report = None
    try:
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
    except Exception as e:
        db.session.rollback()
        log.error(f'DB save error: {e}')

    return render_template('result.html',
        analysis  = analysis,
        filename  = filename,
        report_id = report.id if report else None,
    )

# ─────────────────────────────────────────────
# ROUTES — SYMPTOMS
# ─────────────────────────────────────────────

@app.route('/analyze-symptoms', methods=['GET', 'POST'])
@login_required
def analyze_symptoms_route():
    if request.method == 'POST':
        symptoms = request.form.get('symptoms', '').strip()
        if not symptoms or len(symptoms) < MIN_SYMPTOM_LENGTH:
            return render_template('symptoms.html',
                error='Please describe your symptoms in more detail.')
        symptoms = symptoms[:2000]
        try:
            analysis = analyze_symptoms(symptoms)
        except Exception as e:
            log.error(f'Symptom error: {e}')
            return render_template('symptoms.html', error='Analysis failed. Please try again.')
        return render_template('symptoms_result.html', analysis=analysis, symptoms=symptoms)
    return render_template('symptoms.html')

# ─────────────────────────────────────────────
# ROUTES — IMAGE
# ─────────────────────────────────────────────

@app.route('/analyze-image', methods=['GET', 'POST'])
@login_required
def analyze_image_route():
    if request.method == 'POST':
        image    = request.files.get('image')
        category = request.form.get('category', 'general').strip()
        context  = request.form.get('context', '').strip()[:200]
        if not image or not image.filename:
            return render_template('analyze_image.html', error='Please select an image.')
        if not allowed_image(image.filename):
            return render_template('analyze_image.html', error='Only JPG, PNG, WEBP images are supported.')
        filename = secure_filename(image.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f'aai_img_{filename}')
        try:
            image.save(filepath)
            analysis = analyze_image_with_ai(filepath, filename, category, context)
        except Exception as e:
            log.error(f'Image error: {e}')
            return render_template('analyze_image.html',
                error='Analysis failed. Please try a clearer image.')
        finally:
            _safe_remove(filepath)
        return render_template('image_result.html',
            analysis=analysis, category=category, context=context)
    return render_template('analyze_image.html')

# ─────────────────────────────────────────────
# ROUTES — HISTORY
# ─────────────────────────────────────────────

@app.route('/history')
@login_required
def history():
    page    = request.args.get('page', 1, type=int)
    reports = Report.query.filter_by(user_id=current_user.id)\
        .order_by(Report.created_at.desc())\
        .paginate(page=page, per_page=20, error_out=False)
    return render_template('history.html', reports=reports)


@app.route('/history/<int:report_id>')
@login_required
def view_report(report_id):
    report = Report.query.get_or_404(report_id)
    if report.user_id != current_user.id:
        return redirect(url_for('history'))
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
        analysis=analysis, filename=report.filename, report_id=report.id)

# ─────────────────────────────────────────────
# ROUTES — ACCOUNT
# ─────────────────────────────────────────────

@app.route('/account')
@login_required
def account():
    total_reports  = Report.query.filter_by(user_id=current_user.id).count()
    total_payments = Payment.query.filter_by(user_id=current_user.id, status='paid').count()
    total_spent    = db.session.query(db.func.sum(Payment.amount))\
        .filter_by(user_id=current_user.id, status='paid').scalar() or 0
    recent_reports = Report.query.filter_by(user_id=current_user.id)\
        .order_by(Report.created_at.desc()).limit(5).all()
    return render_template('account.html',
        total_reports  = total_reports,
        total_payments = total_payments,
        total_spent    = int(total_spent) // 100,
        recent_reports = recent_reports,
    )

# ─────────────────────────────────────────────
# ROUTES — PAYMENT
# ─────────────────────────────────────────────

@app.route('/upgrade')
@login_required
def upgrade():
    return render_template('upgrade.html',
        plans=PLANS, razorpay_key=os.getenv('RAZORPAY_KEY_ID', ''))


@app.route('/create-order', methods=['POST'])
@login_required
def create_order():
    try:
        data    = request.get_json()
        plan_id = data.get('plan_id') if data else None
        if plan_id not in PLANS:
            return jsonify(error='Invalid plan.'), 400
        plan  = PLANS[plan_id]
        order = razorpay_client.order.create({
            'amount': plan['price'] * 100, 'currency': 'INR',
            'payment_capture': 1,
            'notes': {'user_id': str(current_user.id), 'plan_id': plan_id}
        })
        payment = Payment(
            razorpay_order_id=order['id'], plan_id=plan_id,
            amount=plan['price']*100, user_id=current_user.id)
        db.session.add(payment)
        db.session.commit()
        return jsonify(order_id=order['id'], amount=plan['price']*100,
            currency='INR', plan_name=plan['name'],
            user_name=current_user.name, user_email=current_user.email)
    except Exception as e:
        db.session.rollback()
        log.error(f'Order error: {e}')
        return jsonify(error='Could not create order.'), 500


@app.route('/payment-success', methods=['POST'])
@login_required
def payment_success():
    try:
        data       = request.get_json()
        order_id   = data.get('razorpay_order_id', '')
        payment_id = data.get('razorpay_payment_id', '')
        signature  = data.get('razorpay_signature', '')
        key_secret = os.getenv('RAZORPAY_KEY_SECRET', '').encode()
        msg        = f'{order_id}|{payment_id}'.encode()
        expected   = hmac_module.new(key_secret, msg, hashlib.sha256).hexdigest()
        if not hmac_module.compare_digest(expected, signature):
            return jsonify(success=False, error='Verification failed.'), 400
        payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
        if not payment:
            return jsonify(success=False, error='Order not found.'), 404
        if payment.status == 'paid':
            return jsonify(success=True, message='Already processed.')
        payment.razorpay_payment_id = payment_id
        payment.status              = 'paid'
        plan = PLANS.get(payment.plan_id, {})
        current_user.reports_limit += plan.get('reports', 0)
        current_user.is_paid        = True
        db.session.commit()
        return jsonify(success=True,
            reports_added=plan.get('reports', 0),
            new_limit=current_user.reports_limit)
    except Exception as e:
        db.session.rollback()
        log.error(f'Payment success error: {e}')
        return jsonify(success=False, error='Something went wrong.'), 500


@app.route('/payment-failed', methods=['POST'])
@login_required
def payment_failed():
    try:
        data     = request.get_json()
        order_id = data.get('razorpay_order_id', '') if data else ''
        payment  = Payment.query.filter_by(razorpay_order_id=order_id).first()
        if payment:
            payment.status = 'failed'
            db.session.commit()
    except Exception as e:
        log.error(f'Payment failed route error: {e}')
    return jsonify(success=True)

# ─────────────────────────────────────────────
# ROUTES — ADMIN
# ─────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users     = User.query.count()
    paid_users      = User.query.filter_by(is_paid=True).count()
    total_reports   = Report.query.count()
    total_revenue   = db.session.query(db.func.sum(Payment.amount))\
        .filter_by(status='paid').scalar() or 0
    recent_users    = User.query.order_by(User.created_at.desc()).limit(10).all()
    recent_payments = Payment.query.filter_by(status='paid')\
        .order_by(Payment.created_at.desc()).limit(10).all()
    return render_template('admin.html',
        total_users=total_users, paid_users=paid_users,
        total_reports=total_reports, total_revenue=int(total_revenue)//100,
        recent_users=recent_users, recent_payments=recent_payments)


@app.route('/admin/add-credits/<int:user_id>/<int:credits>')
@login_required
@admin_required
def admin_add_credits(user_id, credits):
    user = User.query.get_or_404(user_id)
    user.reports_limit += credits
    db.session.commit()
    log.info(f'Admin added {credits} credits to {user.email}')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/toggle-admin/<int:user_id>')
@login_required
@admin_required
def admin_toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id != current_user.id:
        user.is_admin = not user.is_admin
        db.session.commit()
    return redirect(url_for('admin_dashboard'))


@app.route('/setup-admin/<secret>/<email>')
def setup_admin(secret, email):
    if secret != os.getenv('ADMIN_SECRET', 'arogyaai2026secret'):
        return 'Forbidden', 403
    user = User.query.filter_by(email=email).first()
    if not user:
        return 'User not found. Please sign up first.', 404
    user.is_admin = True
    db.session.commit()
    return f'<h2>✅ Success!</h2><p>{user.name} is now admin.</p><a href="/admin">Go to Admin →</a>'

# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Page not found.'), 404


@app.errorhandler(413)
def too_large(e):
    return render_template('index.html',
        error=f'File too large. Maximum {MAX_CONTENT_MB}MB allowed.'), 413


@app.errorhandler(500)
def server_error(e):
    log.error(f'500: {e}')
    return render_template('error.html', code=500,
        message='Something went wrong. Please try again.'), 500


@app.route('/health')
def health():
    return jsonify(status='ok', version='3.0.0'), 200

# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────

with app.app_context():
    db.create_all()
    log.info('ArogyaAI v3.0 started ✅')

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')