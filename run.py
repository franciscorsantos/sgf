from api.index import app

if __name__ == "__main__":
    print("Iniciando Melia Transportes: Modo Local ...")
    # Inicia a aplicação Flask em modo de desenvolvimento
    app.run(debug=True, port=5000)