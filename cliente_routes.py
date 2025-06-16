from flask import Blueprint, render_template, redirect, url_for, session, request, jsonify
from datetime import datetime
from app import db, Cita, BlockedDay, USUARIO_ADMIN, CLAVE_ADMIN, enviar_correo_async, EMAIL_FROM

cliente_bp = Blueprint('cliente', __name__)

@cliente_bp.route('/')
def inicio():
    return redirect(url_for('cliente.login'))

@cliente_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        clave = request.form['clave']
        if usuario == USUARIO_ADMIN and clave == CLAVE_ADMIN:
            session['usuario'] = usuario
            return redirect(url_for('admin.calendario'))
        else:
            return render_template('login.html', error="Usuario o contraseña incorrectos")
    return render_template('login.html')

@cliente_bp.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('cliente.login'))

@cliente_bp.route('/reservar', methods=['GET', 'POST'])
def reservar():
    if request.method == 'POST':
        nombre = request.form['nombre']
        correo = request.form['correo']
        telefono = request.form['telefono']
        servicio = request.form['servicio']
        fecha = request.form.get('hora_seleccionada')
        if not nombre or not correo or not fecha:
            return render_template("reservar.html", error="Todos los campos son obligatorios.")
        cita_existente = Cita.query.filter_by(fecha=fecha).first()
        if cita_existente:
            return render_template("reservar.html", error="Esa franja ya ha sido solicitada.")
        nueva = Cita(
            nombre=nombre,
            correo=correo,
            telefono=telefono,
            fecha=fecha,
            servicio=servicio,
            estado="pendiente"
        )
        db.session.add(nueva)
        db.session.commit()
        # Guardar el correo en la sesión para acceso directo a ver citas
        session['usuario_email'] = correo
        try:
            enviar_correo_async(
                correo,
                "Solicitud de cita recibida",
                f"Hola {nombre},<br>Hemos recibido tu solicitud de cita para el servicio '{servicio}' el {fecha}. Te avisaremos cuando sea aceptada."
            )
            asunto_dueño = f"Nueva solicitud de cita - {nombre}"
            mensaje_dueño = f"""
            <h3>¡Nueva solicitud de cita!</h3>
            <p><strong>Cliente:</strong> {nombre}</p>
            <p><strong>Correo:</strong> {correo}</p>
            <p><strong>Teléfono:</strong> {telefono if telefono else 'No proporcionado'}</p>
            <p><strong>Servicio:</strong> {servicio}</p>
            <p><strong>Fecha y hora:</strong> {fecha}</p>
            <p>Por favor, inicia sesión en el panel de administración para gestionar esta solicitud.</p>
            """
            enviar_correo_async(
                EMAIL_FROM,
                asunto_dueño,
                mensaje_dueño
            )
        except Exception as e:
            print("Error enviando correos:", e)
        # Mostrar mensaje de éxito y ocultar formulario
        return render_template("reservar.html", mensaje="Tu solicitud ha sido enviada. Espera a que sea aceptada por el dueño del negocio. Te contactaremos por correo electrónico.")
    return render_template("reservar.html")

@cliente_bp.route('/mis-citas', methods=['GET', 'POST'])
def mis_citas():
    if request.method == 'POST':
        email = request.form['correo']
        session['usuario_email'] = email
        return redirect(url_for('cliente.ver_citas'))
    return render_template('acceso_citas.html', ocultar_nav=True)

@cliente_bp.route('/ver-citas')
def ver_citas():
    if 'usuario_email' not in session:
        return redirect(url_for('cliente.mis_citas'))
    hoy = datetime.now().isoformat()
    citas = Cita.query.filter_by(correo=session['usuario_email']).order_by(Cita.fecha).all()
    return render_template('ver_citas.html', citas=citas, hoy=hoy, ocultar_nav=True)

@cliente_bp.route('/cancelar-cita/<int:id>', methods=['POST'])
def cancelar_cita(id):
    if 'usuario_email' not in session:
        return redirect(url_for('cliente.mis_citas'))
    cita = Cita.query.get(id)
    if cita and cita.correo == session['usuario_email']:
        # Enviar correo de cancelación antes de borrar
        try:
            enviar_correo_async(
                cita.correo,
                "Cita cancelada",
                f"Hola {cita.nombre},<br>Tu cita para el servicio '{cita.servicio}' el {cita.fecha} ha sido <b>cancelada</b>.<br>Si lo deseas, puedes reservar otra franja horaria desde la web."
            )
        except Exception as e:
            print("Error enviando correo de cancelación:", e)
        db.session.delete(cita)
        db.session.commit()
    return redirect(url_for('cliente.ver_citas'))
