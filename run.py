from app import create_app, db

app = create_app()

if __name__ == '__main__':
    # Crear las tablas de la base de datos si no existen
    with app.app_context():
        db.create_all()
    
    # Iniciar la aplicación en modo debug
    app.run(debug=True, host='0.0.0.0', port=5000)
