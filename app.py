import os
import requests
from flask import Flask, jsonify
from datetime import datetime

app = Flask(__name__)

print("\n" + "="*60)
print("💰 REAL DHAN BALANCE MANAGER - WORKING")
print("="*60)

# Get credentials
ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')

print(f"🔐 Token: {'✅ LOADED' if ACCESS_TOKEN else '❌ MISSING'}")
print(f"🔐 Client ID: {'✅ LOADED' if CLIENT_ID else '❌ MISSING'}")

if ACCESS_TOKEN:
    print(f"📏 Token length: {len(ACCESS_TOKEN)} chars")
    print(f"🔍 Token preview: {ACCESS_TOKEN[:30]}...")

print("="*60)

HEADERS = {
    'access-token': ACCESS_TOKEN,
    'Content-Type': 'application/json'
}

# ==================== WORKING BALANCE FETCH ====================
def get_real_balance():
    """Fetch REAL Dhan balance"""
    try:
        print("\n💰 Fetching REAL balance...")
        response = requests.get(
            'https://api.dhan.co/positions',
            headers=HEADERS,
            timeout=15
        )
        
        print(f"📡 Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Got response")
            
            # Calculate portfolio value
            if isinstance(data, list):
                total = 0
                positions_count = len(data)
                
                for position in data:
                    if isinstance(position, dict):
                        # Try currentValue
                        if 'currentValue' in position:
                            try:
                                value = float(position['currentValue'])
                                total += value
                                continue
                            except:
                                pass
                        
                        # Try calculation
                        if 'ltp' in position and 'quantity' in position:
                            try:
                                ltp = float(position['ltp'])
                                qty = float(position['quantity'])
                                total += ltp * qty
                            except:
                                pass
                
                print(f"📊 Positions: {positions_count}")
                print(f"💰 Total Value: ₹{total:,.2f}")
                return total
            
            return None
            
        elif response.status_code == 401:
            print("❌ ERROR: Token invalid/expired!")
            return None
        else:
            print(f"❌ Error {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None

# ==================== WEB ROUTES ====================
@app.route('/')
def home():
    """Main dashboard"""
    return jsonify({
        'status': 'ACTIVE',
        'system': 'Real Dhan Balance',
        'time': datetime.now().strftime('%H:%M:%S'),
        'endpoints': {
            '/real_balance': 'Get real Dhan balance',
            '/test_api': 'Test API connection',
            '/health': 'Health check'
        }
    })

@app.route('/real_balance')
def real_balance():
    """Get real balance"""
    balance = get_real_balance()
    
    if balance is not None:
        return jsonify({
            'success': True,
            'balance': balance,
            'message': f'Real Dhan Balance: ₹{balance:,.2f}',
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Could not fetch balance',
            'suggestion': 'Check token and try again'
        })

@app.route('/test_api')
def test_api():
    """Test API connection"""
    try:
        response = requests.get(
            'https://api.dhan.co/positions',
            headers=HEADERS,
            timeout=10
        )
        
        return jsonify({
            'status': response.status_code,
            'success': response.status_code == 200,
            'message': 'API working' if response.status_code == 200 else 'API failed',
            'response': response.text[:300] if response.text else 'Empty'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/health')
def health():
    return jsonify({
        'status': 'HEALTHY',
        'time': datetime.now().strftime('%H:%M:%S'),
        'token_loaded': bool(ACCESS_TOKEN)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Server starting on port {port}")
    print(f"📊 URL: https://dhan-auto-real.onrender.com/")
    print("="*60)
    app.run(host='0.0.0.0', port=port, debug=False)