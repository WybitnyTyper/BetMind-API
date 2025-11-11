
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def root():
    return jsonify({"status": "ok", "message": "BetMind API backend is running"})

@app.route('/live')
def live():
    return jsonify({"matches": [], "note": "Live feed will be connected next step"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
