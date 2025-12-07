from flask import Flask, jsonify
import os

app = Flask(__name__)

print("🚀 SIMPLE APP STARTING")

@app.route('/')
def home():
    return jsonify({
        'status': 'WORKING',
        'message': 'System is running',
        'token_loaded': bool(os.environ.get('DHAN_ACCESS_TOKEN'))
    })

@app.route('/health')
def health():
    return jsonify({'health': 'OK'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"Starting on port {port}")
    app.run(host='0.0.0.0', port=port)
