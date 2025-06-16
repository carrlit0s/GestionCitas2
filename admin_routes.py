from flask import Blueprint, render_template, redirect, url_for, session, request, jsonify
from datetime import datetime
from functools import wraps
from app import db, Cita, BlockedDay, enviar_correo_async, EMAIL_FROM

admin_bp = Blueprint('admin', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('cliente.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/calendario')
@login_required
def calendario():
    eventos = [e for e in [cita.to_event() for cita in Cita.query.all()] if e]
    return render_template("calendario.html", citas=eventos)

@admin_bp.route('/horarios_disponibles')
@login_required
def horarios_disponibles():
    fecha = request.args.get('fecha')
    if not fecha:
        return jsonify([])
        
    # Verificar si la fecha está dentro de algún rango de días bloqueados
    bloqueos = BlockedDay.query.all()
    for bloqueo in bloqueos:
        if bloqueo.start_date <= fecha <= bloqueo.end_date:
            return jsonify([])  # No hay horarios disponibles si el día está bloqueado
            
    try:
        dia = datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        return jsonify([])
        
    # Obtener las horas ocupadas por citas existentes
    citas_dia = Cita.query.filter(
        Cita.fecha.startswith(fecha),
        Cita.estado.in_(['aceptada', 'pendiente'])
    ).all()
    
    horas_ocupadas = set()
    for cita in citas_dia:
        try:
            hora_cita = datetime.fromisoformat(cita.fecha).strftime('%H:%M')
        except Exception:
            hora_cita = cita.fecha[11:16]
        horas_ocupadas.add(hora_cita)
    
    # Generar horarios disponibles de 10:00 a 20:00
    horas = []
    for hora in range(10, 21):
        hora_str = f"{hora:02d}:00"
        if hora_str not in horas_ocupadas:
            horas.append(hora_str)
    
    return jsonify(horas)

@admin_bp.route('/solicitudes')
@login_required
def solicitudes():
    pendientes = Cita.query.filter_by(estado='pendiente').all()
    return render_template('solicitudes.html', citas=pendientes)

@admin_bp.route('/aceptar/<int:id>')
@login_required
def aceptar_cita(id):
    cita = Cita.query.get_or_404(id)
    cita.estado = 'aceptada'
    db.session.commit()
    try:
        enviar_correo_async(
            cita.correo,
            "Cita aceptada",
            f"Hola {cita.nombre},<br>Tu cita para el servicio '{cita.servicio}' el {cita.fecha} ha sido <b>aceptada</b>.<br>¡Te esperamos!"
        )
    except Exception as e:
        print("Error enviando correo:", e)
    return redirect(url_for('admin.solicitudes'))

@admin_bp.route('/rechazar/<int:id>')
@login_required
def rechazar_cita(id):
    cita = Cita.query.get_or_404(id)
    db.session.delete(cita)
    db.session.commit()
    return redirect(url_for('admin.solicitudes'))

@admin_bp.route('/api/cita/<int:id>/aceptar', methods=['POST'])
@login_required
def api_aceptar(id):
    cita = Cita.query.get_or_404(id)
    cita.estado = 'aceptada'
    db.session.commit()
    try:
        enviar_correo_async(
            cita.correo,
            "Cita aceptada",
            f"Hola {cita.nombre},<br>Tu cita para el servicio '{cita.servicio}' el {cita.fecha} ha sido <b>aceptada</b>.<br>¡Te esperamos!"
        )
    except Exception as e:
        print("Error enviando correo:", e)
    return 'OK', 200

@admin_bp.route('/api/cita/<int:id>/rechazar', methods=['POST'])
@login_required
def api_rechazar(id):
    cita = Cita.query.get_or_404(id)
    print(f"Intentando enviar correo de rechazo a {cita.correo}")
    # Enviar correo al cliente antes de eliminar
    try:
        enviar_correo_async(
            cita.correo,
            "Cita rechazada",
            f"Hola {cita.nombre},<br>Tu cita para el servicio '{cita.servicio}' el {cita.fecha} ha sido <b>rechazada</b> por el administrador.<br>Por favor, prueba a reservar en otra franja horaria."
        )
    except Exception as e:
        print("Error enviando correo de rechazo:", e)
    db.session.delete(cita)
    db.session.commit()
    return 'OK', 200

@admin_bp.route('/api/cita/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_cita_api(id):
    cita = Cita.query.get_or_404(id)
    if cita.estado != 'aceptada':
        return jsonify(ok=False, error='Solo se pueden eliminar citas aceptadas')
    print(f"Intentando enviar correo de cancelación a {cita.correo}")
    # Enviar correo al cliente antes de eliminar
    try:
        enviar_correo_async(
            cita.correo,
            "Cita cancelada por el administrador",
            f"Hola {cita.nombre},<br>Tu cita para el servicio '{cita.servicio}' el {cita.fecha} ha sido <b>cancelada por el administrador</b>.<br>Si lo deseas, puedes reservar otra franja horaria desde la web."
        )
    except Exception as e:
        print("Error enviando correo de cancelación admin:", e)
    db.session.delete(cita)
    db.session.commit()
    return jsonify(ok=True)

@admin_bp.route('/api/cita/<int:id>/modificar', methods=['POST'])
@login_required
def modificar_cita(id):
    cita = Cita.query.get_or_404(id)
    data = request.get_json()
    nueva_fecha = data.get('nueva_fecha')
    if not nueva_fecha:
        return jsonify(ok=False, error='Fecha no proporcionada')
    conflicto = Cita.query.filter(
        Cita.fecha == nueva_fecha,
        Cita.id != cita.id,
        Cita.estado.in_(['aceptada', 'pendiente'])
    ).first()
    if conflicto:
        return jsonify(ok=False, error='La franja ya está ocupada')
    cita.fecha = nueva_fecha
    db.session.commit()
    return jsonify(ok=True)

@admin_bp.route('/api/cita/manual', methods=['POST'])
@login_required
def crear_cita_manual():
    data = request.get_json()
    nombre = data.get('nombre')
    fecha = data.get('fecha')
    if not nombre or not fecha:
        return jsonify(ok=False, error='Nombre y fecha requeridos')
    conflicto = Cita.query.filter(
        Cita.fecha == fecha,
        Cita.estado.in_(['aceptada', 'pendiente'])
    ).first()
    if conflicto:
        return jsonify(ok=False, error='La franja ya está ocupada')
    nueva = Cita(
        nombre=nombre,
        correo='manual@local',
        telefono='',
        fecha=fecha,
        servicio='Manual',
        estado='aceptada'
    )
    db.session.add(nueva)
    db.session.commit()
    return jsonify(ok=True)

@admin_bp.route('/admin/bloquear-dias', methods=['GET', 'POST'])
@login_required
def bloquear_dias():
    mensaje = None
    if request.method == 'POST':
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        motivo = request.form.get('motivo', '')
        
        bloqueado = BlockedDay(
            start_date=start_date, 
            end_date=end_date,
            motivo=motivo
        )
        db.session.add(bloqueado)
        try:
            db.session.commit()
            mensaje = 'Días bloqueados correctamente.'
        except Exception as e:
            db.session.rollback()
            mensaje = f'Error al guardar el bloqueo: {str(e)}', 'error'
    
    # Ordenar por fecha de inicio
    bloqueos = BlockedDay.query.order_by(BlockedDay.start_date.desc()).all()
    return render_template('bloquear_dias.html', bloqueos=bloqueos, mensaje=mensaje)

@admin_bp.route('/admin/bloquear-dias/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_bloqueo(id):
    bloqueo = BlockedDay.query.get_or_404(id)
    db.session.delete(bloqueo)
    db.session.commit()
    return redirect(url_for('admin.bloquear_dias'))

@admin_bp.route('/api/dias-bloqueados')
@login_required
def api_dias_bloqueados():
    try:
        bloqueos = BlockedDay.query.all()
        eventos = []
        for bloqueo in bloqueos:
            try:
                evento = bloqueo.to_event()
                if evento:  # Solo añadir si to_event() devuelve algo
                    eventos.append(evento)
            except Exception as e:
                print(f"Error al convertir bloqueo a evento: {e}")
                continue
        return jsonify(eventos)
    except Exception as e:
        print(f"Error en api_dias_bloqueados: {e}")
        return jsonify([])  # Devolver una lista vacía en caso de error

def esta_hora_bloqueada(fecha_str, hora_str):
    """Verifica si una hora específica está bloqueada."""
    if not fecha_str or not hora_str:
        return False
        
    # Convertir la hora a formato HH:MM para comparación
    try:
        hora_deseada = datetime.strptime(hora_str, '%H:%M').time()
    except ValueError:
        return False
    
    # Buscar bloqueos que afecten a esta fecha
    bloqueos = BlockedDay.query.filter(
        BlockedDay.start_date <= fecha_str,
        BlockedDay.end_date >= fecha_str
    ).all()
    
    for bloqueo in bloqueos:
        # Si no hay horas definidas, todo el día está bloqueado
        if not bloqueo.start_time or not bloqueo.end_time:
            return True
            
        # Si hay horas definidas, verificar si la hora cae dentro del rango
        try:
            hora_inicio = datetime.strptime(bloqueo.start_time, '%H:%M').time()
            hora_fin = datetime.strptime(bloqueo.end_time, '%H:%M').time()
            
            # Solo aplicar el bloqueo si es el mismo día
            if bloqueo.start_date == fecha_str and bloqueo.end_date == fecha_str:
                if hora_inicio <= hora_deseada < hora_fin:
                    return True
        except ValueError:
            continue
            
    return False
