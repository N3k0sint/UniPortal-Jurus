from uniklpj_portal import create_app

app = create_app()

if __name__ == '__main__':
    # Flask development server (only used when running directly in local dev)
    app.run(host='127.0.0.1', port=5000)
