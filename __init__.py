from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from flask_migrate import Migrate
import os

# Inicialización de la app y configuración
app = Flask(__name__)
app.secret_key = 'clave-secreta-segura'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'citas.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Modelos
class Cita(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20), nullable=True)
    fecha = db.Column(db.String(20), nullable=False)
    servicio = db.Column(db.String(100), nullable=True)
    estado = db.Column(db.String(20), nullable=False, default="pendiente")

    def to_event(self):
        color = "#999"
        if self.estado == "aceptada":
            color = "#28a745"
        elif self.estado == "pendiente":
            color = "#ffc107"
        elif self.estado == "rechazada":
            return None
        return {
            "id": self.id,
            "title": f"{self.nombre} ({self.estado})",
            "start": self.fecha,
            "color": color,
            "extendedProps": {
                "nombre": self.nombre,
                "correo": self.correo,
                "telefono": self.telefono,
                "estado": self.estado,
                "servicio": self.servicio
            }
        }

class BlockedDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.String(20), nullable=False)
    end_date = db.Column(db.String(20), nullable=False)
    motivo = db.Column(db.String(200), nullable=True)
    
    def to_event(self):
        # Añadir un día al final para que el bloqueo incluya todo el día de end_date
        end_date = datetime.strptime(self.end_date, '%Y-%m-%d') + timedelta(days=1)
        end = end_date.strftime('%Y-%m-%d')
        
        return {
            'id': f'bloqueo_{self.id}',
            'title': 'Día bloqueado' + (f': {self.motivo}' if self.motivo else ''),
            'start': self.start_date,
            'end': end,
            'color': '#dc3545',
            'allDay': True,
            'extendedProps': {
                'motivo': self.motivo or 'Sin motivo especificado',
                'tipo': 'bloqueo'
            }
        }

# Configuración de correo y utilidades
USUARIO_ADMIN = "admin"
CLAVE_ADMIN = "pelu123"
EMAIL_FROM = "burritopspva@gmail.com"
EMAIL_PASS = "kbkurmpzvxgnafav"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

import smtplib
from email.mime.text import MIMEText
import threading

def enviar_correo(destino, asunto, mensaje):
    msg = MIMEText(mensaje, "html")
    msg['Subject'] = asunto
    msg['From'] = EMAIL_FROM
    msg['To'] = destino
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASS)
            server.sendmail(EMAIL_FROM, [destino], msg.as_string())
    except Exception as e:
        print(f"Error enviando correo a {destino}: {e}")

def enviar_correo_async(destino, asunto, mensaje):
    hilo = threading.Thread(target=enviar_correo, args=(destino, asunto, mensaje))
    hilo.daemon = True
    hilo.start()

# Importar rutas para registrar los blueprints
from .cliente_routes import cliente_bp
from .admin_routes import admin_bp

def create_app():
    with app.app_context():
        db.create_all()
    app.register_blueprint(cliente_bp)
    app.register_blueprint(admin_bp)
    return app
